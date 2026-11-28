using System;
using System.Collections.Generic;
using System.ComponentModel;
using System.Diagnostics;
using System.Globalization;
using System.Runtime.InteropServices;
using System.Threading;
using Microsoft.Win32.SafeHandles;

namespace BilletT1
{
    public sealed class Transaction
    {
        public string Utc { get; set; }
        public string Operation { get; set; }
        public int Word { get; set; }
        public string ValueHex { get; set; }
    }

    public sealed class FrameResult
    {
        public int frame_index { get; set; }
        public int transaction_start { get; set; }
        public int transaction_count { get; set; }
        public ulong status { get; set; }
        public ulong csr15_before { get; set; }
        public ulong csr15_after { get; set; }
        public uint expected_component_clamps { get; set; }
        public ulong cycles { get; set; }
        public ulong elapsed_ddr_cycles { get; set; }
        public long host_start_tick { get; set; }
        public long host_end_tick { get; set; }
    }

    public sealed class VectorResult
    {
        public string id { get; set; }
        public ulong cycles { get; set; }
        public ulong elapsed_ddr_cycles { get; set; }
        public FrameResult[] frames { get; set; }
        public Dictionary<string, object> telemetry { get; set; }
        public Dictionary<string, ulong>[] transactions { get; set; }
        public string output_hex { get; set; }
    }

    public sealed class SoftRegisters : IDisposable
    {
        private const int Points = 256;
        private const int MaxStatusPolls = 128;
        private readonly SafeFileHandle handle;
        private readonly IntPtr bar;
        private readonly List<Dictionary<string, ulong>> transactions = new List<Dictionary<string, ulong>>();
        private ulong? lastClampCsr;

        [DllImport("kernel32.dll", CharSet = CharSet.Unicode, ExactSpelling = true, SetLastError = true)]
        private static extern SafeFileHandle CreateFileW(string path, uint access, uint share,
            IntPtr attributes, uint disposition, uint flags, IntPtr template);

        [DllImport("kernel32.dll", ExactSpelling = true, SetLastError = true)]
        [return: MarshalAs(UnmanagedType.Bool)]
        private static extern bool DeviceIoControl(SafeFileHandle device, uint code,
            IntPtr input, uint inputBytes, [Out] byte[] output, uint outputBytes,
            out uint returned, IntPtr overlapped);

        public SoftRegisters(string path)
        {
            if (IntPtr.Size != 8 || path == null || !path.StartsWith(@"\\?\PCI#", StringComparison.OrdinalIgnoreCase))
                throw new ArgumentException("Expected a 64-bit managed NETSYS17 PCI device path.");
            handle = CreateFileW(path, 0xC0000000U, 3U, IntPtr.Zero, 3U, 0U, IntPtr.Zero);
            if (handle.IsInvalid)
                throw new Win32Exception(Marshal.GetLastWin32Error(), "Opening the managed PCI device failed.");
            byte[] response = new byte[16];
            uint returned;
            if (!DeviceIoControl(handle, 0xB0B28004U, IntPtr.Zero, 0U, response, 16U, out returned, IntPtr.Zero))
            {
                int error = Marshal.GetLastWin32Error();
                handle.Dispose();
                throw new Win32Exception(error, "Mapping BAR0 failed.");
            }
            if (returned != 16 || BitConverter.ToInt64(response, 0) == 0)
            {
                handle.Dispose();
                throw new InvalidOperationException("BAR0 mapping returned no valid pointer.");
            }
            bar = new IntPtr(BitConverter.ToInt64(response, 0));
        }

        private IntPtr Address(int word)
        {
            if (word < 0 || word > 0x3ffff)
                throw new ArgumentOutOfRangeException("word");
            return IntPtr.Add(bar, 0x800000 + 8 * word);
        }

        private static string Hex(ulong value)
        {
            return "0x" + value.ToString("x16", CultureInfo.InvariantCulture);
        }

        private ulong ReadValue(int word)
        {
            IntPtr address = Address(word);
            Thread.MemoryBarrier();
            ulong value = unchecked((ulong)Marshal.ReadInt64(address));
            Thread.MemoryBarrier();
            return value;
        }

        private void WriteValue(int word, ulong value)
        {
            IntPtr address = Address(word);
            Thread.MemoryBarrier();
            Marshal.WriteInt64(address, unchecked((long)value));
            Thread.MemoryBarrier();
        }

        private ulong Read(int word)
        {
            ulong value = ReadValue(word);
            transactions.Add(new Dictionary<string, ulong> { { "r", (ulong)word }, { "v", value } });
            return value;
        }

        private void Write(int word, ulong value)
        {
            WriteValue(word, value);
            transactions.Add(new Dictionary<string, ulong> { { "w", (ulong)word }, { "v", value } });
        }

        private Transaction Observe(int word)
        {
            return new Transaction {
                Word = word, Operation = "read", ValueHex = Hex(ReadValue(word)),
                Utc = DateTime.UtcNow.ToString("o", CultureInfo.InvariantCulture)
            };
        }

        public Transaction[] VerifyIdentity(string expectedMagic)
        {
            Transaction[] identity = { Observe(0), Observe(1), Observe(9) };
            if (identity[0].ValueHex != expectedMagic || identity[1].ValueHex != Hex(0x0002000000024254UL) ||
                identity[2].ValueHex != Hex(Points))
                throw new InvalidOperationException("Unexpected Billet-T1 magic, role identity, or frame size.");
            return identity;
        }

        private static void Require(bool ok, string context, string message)
        {
            if (!ok)
                throw new InvalidOperationException(context + ": " + message);
        }

        private FrameResult RunFrame(string id, int index, uint[] samples, byte[] packed,
                                     uint increment, Stopwatch clock)
        {
            string context = id + "[" + index + "]";
            long start = clock.ElapsedTicks;
            int transactionStart = transactions.Count;
            int offset = index * Points;
            Require((Read(2) & 1) == 0, context, "Role is busy before staging.");
            ulong before = Read(15);
            ulong beforeCount = before >> 1;
            Require(beforeCount <= uint.MaxValue && ((before & 1) != 0) == (beforeCount != 0) &&
                    (!lastClampCsr.HasValue || lastClampCsr.Value == before),
                    context, "Unexpected clamp state before clear: " + Hex(before));
            Write(3, 4);
            Write(4, 0);
            ulong idle = Read(2);
            ulong mode = Read(4);
            ulong clearedClamp = Read(15);
            Require(idle == 0 && mode == 0 && clearedClamp == before,
                    context, "Clear did not leave idle staged mode with unchanged clamp state.");
            ulong jobsBefore = Read(14);

            for (int i = 0; i < Points; i++)
                Write(0x1000 + i, samples[offset + i]);
            for (int i = 0; i < Points; i++)
            {
                ulong staged = Read(0x1000 + i);
                if (staged != samples[offset + i])
                    throw new InvalidOperationException(context + ": staged sample " + i +
                        " expected " + Hex(samples[offset + i]) + ", read " + Hex(staged));
            }

            Write(3, 1);
            Stopwatch pollClock = Stopwatch.StartNew();
            ulong status = 0;
            for (int poll = 0; poll < MaxStatusPolls; poll++)
            {
                status = Read(2);
                if ((status & 4) != 0)
                    throw new InvalidOperationException(context + ": role error code " + Read(10));
                if (status == 2 || pollClock.ElapsedMilliseconds >= 10000)
                    break;
                Thread.Sleep(poll < 7 ? 2 : 100);
            }
            Require(status == 2, context, "FFT timed out, last status " + Hex(status));
            ulong cycles = Read(11);
            ulong elapsed = Read(20);
            ulong jobsAfter = Read(14);
            ulong counts = Read(21);
            ulong ddr = Read(12);
            ulong pcie = Read(13);
            Require(cycles > 0 && elapsed >= cycles && jobsBefore <= uint.MaxValue &&
                    jobsAfter == ((jobsBefore + 1) & uint.MaxValue) && counts == 0x01000100 &&
                    ddr == 0 && pcie == 0, context, "Invalid completion or cycle/transport telemetry.");
            ulong after = Read(15);
            ulong expectedCount = Math.Min((ulong)uint.MaxValue, beforeCount + increment);
            ulong expectedSticky = (before & 1) | (increment == 0 ? 0UL : 1UL);
            ulong expectedCsr = (expectedCount << 1) | expectedSticky;
            Require(after == expectedCsr, context, "CSR 15 expected " + Hex(expectedCsr) +
                    ", read " + Hex(after) + " after starting at " + Hex(before));
            lastClampCsr = after;

            for (int i = 0; i < Points; i++)
            {
                ulong word = Read(0x2000 + i);
                if (word > uint.MaxValue || (i < 4 && Read(16 + i) != word))
                    throw new InvalidOperationException(context + ": output lane/telemetry mismatch at bin " + i);
                for (int b = 0; b < 4; b++)
                    packed[4 * (offset + i) + b] = (byte)((word >> (8 * b)) & 255);
            }
            Require(Read(2) == 2, context, "Role left the done state while reading bins.");
            return new FrameResult {
                frame_index = index, transaction_start = transactionStart,
                transaction_count = transactions.Count - transactionStart,
                status = status, csr15_before = before, csr15_after = after,
                expected_component_clamps = increment, cycles = cycles, elapsed_ddr_cycles = elapsed,
                host_start_tick = start, host_end_tick = clock.ElapsedTicks
            };
        }

        public VectorResult RunVector(string id, uint[] samples, uint[] increments, Stopwatch clock)
        {
            Require((increments.Length == 1 || increments.Length == 16) &&
                    samples.Length == increments.Length * Points, id, "Frame size differs from clamp plan.");
            transactions.Clear();
            FrameResult[] frames = new FrameResult[increments.Length];
            byte[] packed = new byte[samples.Length * 4];
            ulong cycles = 0;
            ulong elapsed = 0;
            for (int i = 0; i < frames.Length; i++)
            {
                frames[i] = RunFrame(id, i, samples, packed, increments[i], clock);
                cycles += frames[i].cycles;
                elapsed += frames[i].elapsed_ddr_cycles;
            }
            long vectorTicks = frames[frames.Length - 1].host_end_tick - frames[0].host_start_tick;
            Require(vectorTicks > 0, id, "Monotonic host clock did not advance.");
            return new VectorResult {
                id = id, cycles = cycles, elapsed_ddr_cycles = elapsed, frames = frames,
                telemetry = new Dictionary<string, object> {
                    { "kernel_counter_hex", cycles.ToString("x16", CultureInfo.InvariantCulture) },
                    { "host_elapsed_ns", (long)Math.Ceiling(vectorTicks * 1000000000.0 / Stopwatch.Frequency) }
                },
                transactions = transactions.ToArray(),
                output_hex = BitConverter.ToString(packed).Replace("-", "").ToLowerInvariant()
            };
        }

        public void Dispose()
        {
            handle.Dispose();
        }
    }
}
