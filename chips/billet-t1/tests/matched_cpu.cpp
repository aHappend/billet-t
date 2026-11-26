#include <algorithm>
#include <array>
#include <chrono>
#include <cstdint>
#include <fstream>
#include <iostream>
#include <stdexcept>
#include <string>
#include <vector>

namespace {
constexpr unsigned n = 256, frames = 256, warmups = 5, reps = 30;
constexpr std::array<unsigned, 3> batches{1, 16, 256};
using Word = std::uint32_t;
using Clock = std::chrono::steady_clock;
volatile Word observed;

struct Complex {
    int re;
    int im;
};

int signed16(Word x) {
    return static_cast<int>(x & 32767) - static_cast<int>(x & 32768);
}

Complex unpack(Word w) {
    return {signed16(w), signed16(w >> 16)};
}

Word pack(Complex z) {
    return (static_cast<Word>(z.re) & 65535) | (static_cast<Word>(z.im) << 16);
}

int floor_div(std::int64_t x, unsigned shift) {
    const auto d = std::int64_t{1} << shift;
    return static_cast<int>(x < 0 ? -((-x + d - 1) / d) : x / d);
}

int clip(int x) {
    return std::clamp(x, -32768, 32767);
}

constexpr std::array<unsigned, n> bit_reverse() {
    std::array<unsigned, n> r{};
    for (unsigned i = 1; i < n; ++i) {
        r[i] = (r[i / 2] >> 1) | ((i & 1U) * (n / 2));
    }
    return r;
}

[[gnu::noinline]] void fft_batch(const Word* in, Word* out, unsigned count,
                                 const std::array<Complex, n / 2>& tw) {
    constexpr auto reverse = bit_reverse();
    for (unsigned f = 0; f < count; ++f) {
        std::array<Complex, n> a;
        for (unsigned j = 0; j < n; ++j) a[j] = unpack(in[f * n + reverse[j]]);
        for (unsigned half = 1; half < n; half *= 2) {
            for (unsigned start = 0; start < n; start += 2 * half) {
                for (unsigned j = 0; j < half; ++j) {
                    const auto p = start + j, q = p + half;
                    const auto x = a[p], y = a[q], w = tw[j * (n / (2 * half))];
                    const int tr = floor_div(std::int64_t{y.re} * w.re - std::int64_t{y.im} * w.im, 15);
                    const int ti = floor_div(std::int64_t{y.re} * w.im + std::int64_t{y.im} * w.re, 15);
                    a[p] = {clip(floor_div(x.re + tr, 1)), clip(floor_div(x.im + ti, 1))};
                    a[q] = {clip(floor_div(x.re - tr, 1)), clip(floor_div(x.im - ti, 1))};
                }
            }
        }
        for (unsigned j = 0; j < n; ++j) out[f * n + j] = pack(a[j]);
    }
}

Word load(std::istream& f) {
    unsigned char b[4];
    if (!f.read(reinterpret_cast<char*>(b), sizeof(b))) throw std::runtime_error("Truncated benchmark corpus");
    return Word{b[0]} | (Word{b[1]} << 8) | (Word{b[2]} << 16) | (Word{b[3]} << 24);
}

int run(const char* corpus, bool probe) {
    std::ifstream file(corpus, std::ios::binary);
    if (!file) throw std::runtime_error("Cannot open benchmark corpus");
    std::array<Complex, n / 2> tw;
    for (auto& z : tw) z = unpack(load(file));
    std::vector<Word> host_input(n * frames), expected(n * frames), input(n * frames), output(n * frames),
        host_output(n * frames);
    for (Word& x : host_input) x = load(file);
    for (Word& x : expected) x = load(file);
    if (file.peek() != std::char_traits<char>::eof()) throw std::runtime_error("Unexpected trailing corpus data");
    std::copy(host_input.begin(), host_input.end(), input.begin());
    fft_batch(input.data(), output.data(), frames, tw);
    const auto mismatch = std::mismatch(expected.begin(), expected.end(), output.begin());
    if (mismatch.first != expected.end()) {
        std::cerr << "FFT mismatch at packed bin " << mismatch.first - expected.begin()
                  << ": expected 0x" << std::hex << *mismatch.first << ", got 0x" << *mismatch.second << '\n';
        return 2;
    }
    std::cout << "verified " << output.size() << '\n';
    if (probe) return 0;
    for (unsigned batch : batches) {
        for (bool inclusive : {false, true}) {
            const char* boundary = inclusive ? "transfer_inclusive" : "kernel_only";
            for (unsigned i = 0; i < warmups + reps; ++i) {
                const auto t0 = Clock::now();
                if (inclusive) std::copy_n(host_input.data(), batch * n, input.data());
                fft_batch(input.data(), output.data(), batch, tw);
                if (inclusive) std::copy_n(output.data(), batch * n, host_output.data());
                const auto t1 = Clock::now();
                observed = (inclusive ? host_output : output)[batch * n - 1];
                if (i >= warmups) {
                    std::cout << batch << ' ' << boundary << ' '
                              << std::chrono::duration_cast<std::chrono::nanoseconds>(t1 - t0).count() << '\n';
                }
            }
        }
    }
    return 0;
}
}

int main(int argc, char** argv) {
    try {
        if (argc != 2 && !(argc == 3 && std::string(argv[2]) == "--correctness-only"))
            throw std::runtime_error("Usage: matched_cpu CORPUS [--correctness-only]");
        return run(argv[1], argc == 3);
    } catch (const std::exception& e) {
        std::cerr << e.what() << '\n';
        return 1;
    }
}
