#include <cuda_runtime.h>

#include <array>
#include <chrono>
#include <cmath>
#include <cstdint>
#include <cstdlib>
#include <fstream>
#include <iostream>
#include <stdexcept>
#include <string>
#include <vector>

namespace {
constexpr unsigned log_n = 8, n = 1U << log_n, frames = 256, warmups = 5, reps = 30;
constexpr std::array<unsigned, 3> batches{1, 16, frames};
using Word = std::uint32_t;
using Clock = std::chrono::steady_clock;
static_assert((std::int64_t{-1} >> 1) == -1 && (-1 >> 1) == -1);

void check(cudaError_t result, const char* call) {
    if (result != cudaSuccess)
        throw std::runtime_error(std::string(call) + ": " + cudaGetErrorString(result));
}

#define CUDA_CHECK(call) check((call), #call)

__device__ int signed16(Word bits) {
    return static_cast<int>(bits & 0x7fffU) - static_cast<int>(bits & 0x8000U);
}

__device__ Word scaled_bin(int re, int im) {
    re = max(-32768, min(32767, re >> 1));
    im = max(-32768, min(32767, im >> 1));
    return (static_cast<Word>(re) & 0xffffU) | (static_cast<Word>(im) << 16);
}

__global__ void fft(const Word* __restrict__ input, Word* __restrict__ output,
                    const Word* __restrict__ twiddles) {
    __shared__ Word samples[n];
    const unsigned lane = threadIdx.x, base = blockIdx.x * n;
    samples[__brev(lane) >> (32 - log_n)] = input[base + lane];
    samples[__brev(lane + n / 2) >> (32 - log_n)] = input[base + lane + n / 2];
    __syncthreads();

    #pragma unroll
    for (unsigned half = 1; half < n; half *= 2) {
        const unsigned j = lane & (half - 1);
        const unsigned p = 2 * (lane - j) + j, q = p + half;
        const Word a = samples[p], b = samples[q], w = twiddles[j * (n / (2 * half))];
        const int ar = signed16(a), ai = signed16(a >> 16);
        const int br = signed16(b), bi = signed16(b >> 16);
        const int wr = signed16(w), wi = signed16(w >> 16);
        // Each product fits in int, but the complex sum needs a signed 33rd bit.
        const int tr = static_cast<int>((std::int64_t{br * wr} - bi * wi) >> 15);
        const int ti = static_cast<int>((std::int64_t{br * wi} + bi * wr) >> 15);
        const Word lo = scaled_bin(ar + tr, ai + ti), hi = scaled_bin(ar - tr, ai - ti);
        if (half == n / 2) {
            output[base + p] = lo;
            output[base + q] = hi;
        } else {
            samples[p] = lo;
            samples[q] = hi;
            __syncthreads();
        }
    }
}

void launch(unsigned batch, const Word* input, Word* output, const Word* twiddles,
            cudaStream_t stream) {
    fft<<<batch, n / 2, 0, stream>>>(input, output, twiddles);
    CUDA_CHECK(cudaGetLastError());
}

Word load(std::istream& file) {
    unsigned char b[4];
    if (!file.read(reinterpret_cast<char*>(b), sizeof(b)))
        throw std::runtime_error("Truncated benchmark corpus");
    return Word{b[0]} | (Word{b[1]} << 8) | (Word{b[2]} << 16) | (Word{b[3]} << 24);
}

std::string uuid_string(const cudaUUID_t& uuid) {
    constexpr char hex[] = "0123456789abcdef";
    std::string result = "GPU-";
    for (unsigned i = 0; i < sizeof(uuid.bytes); ++i) {
        if (i == 4 || i == 6 || i == 8 || i == 10) result += '-';
        const auto byte = static_cast<unsigned char>(uuid.bytes[i]);
        result += hex[byte >> 4];
        result += hex[byte & 15];
    }
    return result;
}

int run(const char* corpus, const std::string& selected) {
    const char* visible = std::getenv("CUDA_VISIBLE_DEVICES");
    if (!visible || selected != visible || selected.rfind("GPU-", 0) != 0)
        throw std::runtime_error("The managed CUDA check must expose the requested GPU UUID");
    std::ifstream file(corpus, std::ios::binary);
    if (!file) throw std::runtime_error("Cannot open benchmark corpus");

    int count = 0;
    CUDA_CHECK(cudaGetDeviceCount(&count));
    if (count != 1) throw std::runtime_error("Expected exactly one visible CUDA device");
    cudaDeviceProp device{};
    CUDA_CHECK(cudaGetDeviceProperties(&device, 0));
    const auto actual = uuid_string(device.uuid);
    if (actual != selected)
        throw std::runtime_error("Selected GPU " + selected + ", but CUDA observed " + actual);
    CUDA_CHECK(cudaSetDevice(0));
    int runtime_version = 0, driver_version = 0;
    CUDA_CHECK(cudaRuntimeGetVersion(&runtime_version));
    CUDA_CHECK(cudaDriverGetVersion(&driver_version));
    std::cout << "{\"gpu_uuid\":\"" << actual << "\",\"compute_capability\":\""
              << device.major << '.' << device.minor << "\",\"cuda_runtime_version\":" << runtime_version
              << ",\"cuda_driver_version\":" << driver_version << ",\"host_buffers\":\"page_locked\"}\n";

    constexpr unsigned words = n * frames, twiddle_words = n / 2;
    constexpr auto bytes = words * sizeof(Word);
    constexpr auto twiddle_bytes = twiddle_words * sizeof(Word);
    std::vector<Word> expected(words);
    Word *host_corpus = nullptr, *host_output = nullptr;
    Word *input = nullptr, *output = nullptr, *device_twiddles = nullptr;
    CUDA_CHECK(cudaMallocHost(&host_corpus, twiddle_bytes + bytes));
    CUDA_CHECK(cudaMallocHost(&host_output, bytes));
    for (unsigned i = 0; i < twiddle_words + words; ++i) host_corpus[i] = load(file);
    for (Word& x : expected) x = load(file);
    if (file.peek() != std::char_traits<char>::eof()) throw std::runtime_error("Unexpected trailing corpus data");
    if (file.bad()) throw std::runtime_error("Error reading benchmark corpus");
    const Word* host_input = host_corpus + twiddle_words;

    CUDA_CHECK(cudaMalloc(&input, bytes));
    CUDA_CHECK(cudaMalloc(&output, bytes));
    CUDA_CHECK(cudaMalloc(&device_twiddles, twiddle_bytes));
    cudaStream_t stream;
    CUDA_CHECK(cudaStreamCreateWithFlags(&stream, cudaStreamNonBlocking));
    CUDA_CHECK(cudaMemcpyAsync(device_twiddles, host_corpus, twiddle_bytes, cudaMemcpyHostToDevice, stream));
    CUDA_CHECK(cudaMemcpyAsync(input, host_input, bytes, cudaMemcpyHostToDevice, stream));
    launch(frames, input, output, device_twiddles, stream);
    CUDA_CHECK(cudaMemcpyAsync(host_output, output, bytes, cudaMemcpyDeviceToHost, stream));
    CUDA_CHECK(cudaStreamSynchronize(stream));
    for (unsigned i = 0; i < words; ++i) {
        if (host_output[i] != expected[i]) {
            std::cerr << "FFT mismatch at frame " << i / n << ", bin " << i % n
                      << ": expected 0x" << std::hex << expected[i] << ", got 0x" << host_output[i] << '\n';
            return 2;
        }
    }
    std::cout << "verified " << words << '\n';

    cudaEvent_t start, stop;
    CUDA_CHECK(cudaEventCreate(&start));
    CUDA_CHECK(cudaEventCreate(&stop));
    for (unsigned batch : batches) {
        const auto batch_bytes = batch * n * sizeof(Word);
        for (bool inclusive : {false, true}) {
            const char* boundary = inclusive ? "transfer_inclusive" : "kernel_only";
            for (unsigned i = 0; i < warmups + reps; ++i) {
                std::int64_t ns;
                if (inclusive) {
                    const auto t0 = Clock::now();
                    CUDA_CHECK(cudaMemcpyAsync(input, host_input, batch_bytes, cudaMemcpyHostToDevice, stream));
                    launch(batch, input, output, device_twiddles, stream);
                    CUDA_CHECK(cudaMemcpyAsync(host_output, output, batch_bytes, cudaMemcpyDeviceToHost, stream));
                    CUDA_CHECK(cudaStreamSynchronize(stream));
                    ns = std::chrono::duration_cast<std::chrono::nanoseconds>(Clock::now() - t0).count();
                } else {
                    CUDA_CHECK(cudaEventRecord(start, stream));
                    launch(batch, input, output, device_twiddles, stream);
                    CUDA_CHECK(cudaEventRecord(stop, stream));
                    CUDA_CHECK(cudaEventSynchronize(stop));
                    float ms = 0;
                    CUDA_CHECK(cudaEventElapsedTime(&ms, start, stop));
                    ns = std::llround(static_cast<double>(ms) * 1'000'000);
                }
                if (i >= warmups) std::cout << batch << ' ' << boundary << ' ' << ns << '\n';
            }
        }
    }
    CUDA_CHECK(cudaEventDestroy(stop));
    CUDA_CHECK(cudaEventDestroy(start));
    CUDA_CHECK(cudaStreamDestroy(stream));
    CUDA_CHECK(cudaFree(device_twiddles));
    CUDA_CHECK(cudaFree(output));
    CUDA_CHECK(cudaFree(input));
    CUDA_CHECK(cudaFreeHost(host_output));
    CUDA_CHECK(cudaFreeHost(host_corpus));
    return 0;
}
}

int main(int argc, char** argv) {
    try {
        if (argc != 3) throw std::runtime_error("Usage: matched_gpu CORPUS GPU_UUID");
        return run(argv[1], argv[2]);
    } catch (const std::exception& e) {
        std::cerr << e.what() << '\n';
        return 1;
    }
}
