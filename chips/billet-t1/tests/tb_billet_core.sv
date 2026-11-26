`timescale 1ns/1ps

module billet_core_case #(parameter int N = 2) (output bit finished);
    localparam int C = N * $clog2(N);
    bit clk, rst_n, in_valid, in_last, out_ready;
    always #5 begin
        if (!clk) cycle++;
        clk = !clk;
    end
    logic signed [15:0] in_re, in_im, out_re, out_im;
    wire in_ready, out_valid, out_last, frame_done, overflow_flag;
    wire [$clog2(N)-1:0] out_bin_idx;
    wire [31:0] saturation_count;
    billet_t1_top #(.N_POINTS(N)) dut (.*);

    logic [31:0] samples [N], expected [N];
    int cycle, fd, frame_count, kind, f, clamps, seed_count, first, next_valid;
    int inputs, outputs, stalled, completed, stall_left, post_reset;
    logic [31:0] total;
    string base;

    task automatic idle_payload;
        if ({out_re, out_im, out_bin_idx, out_last} !== '0)
            $fatal(1, "CORE_PROTOCOL N=%0d invalid payload not zero at cycle %0d", N, cycle);
    endtask

    task automatic reset_core;
        @(negedge clk);
        rst_n = 0;
        in_valid = 0;
        out_ready = 0;
        repeat (3) @(negedge clk);
        if ({in_ready, out_valid, frame_done, overflow_flag, saturation_count} !== '0)
            $fatal(1, "CORE_PROTOCOL N=%0d stale control/telemetry during reset", N);
        idle_payload();
        rst_n = 1;
        total = 0;
        @(posedge clk);
        #1;
        if (!in_ready || out_valid || frame_done)
            $fatal(1, "CORE_PROTOCOL N=%0d failed to recover from reset", N);
    endtask

    task automatic drive_input(input int index);
        in_re = samples[index][15:0];
        in_im = samples[index][31:16];
        in_last = index == 0;
    endtask

    task automatic abandon_frame(input int stage);
        for (int i = 0; i < (stage == 0 ? N/2 : N); i++) begin
            @(negedge clk);
            drive_input(i);
            in_valid = 1;
            @(posedge clk);
            if (!in_ready)
                $fatal(1, "CORE_PROTOCOL N=%0d incomplete reset setup", N);
        end
        @(negedge clk);
        in_valid = 0;
        if (stage == 1) repeat (2) @(negedge clk);
        if (stage == 2) begin
            repeat (C+2) @(negedge clk);
            if (!out_valid)
                $fatal(1, "CORE_PROTOCOL N=%0d reset did not reach a stalled bin", N);
        end
        reset_core();
        post_reset++;
    endtask

    task automatic run_frame(input int idx);
        inputs = 0;
        outputs = 0;
        stalled = 0;
        first = -1;
        next_valid = -1;
        stall_left = 3;
        while (outputs < N) begin
            bit expect_valid, previous_done, take, final_take, still_loading;
            @(negedge clk);
            still_loading = inputs < N;
            in_valid = !still_loading || (cycle % 5 != 0 && cycle % 5 != 1);
            drive_input(still_loading ? inputs : 0);
            out_ready = !out_valid || stall_left == 0 || outputs % 3 != 0;
            if (out_valid && !out_ready) stall_left--;
            @(posedge clk);
            expect_valid = next_valid >= 0 && cycle >= next_valid;
            previous_done = (idx != 0 && inputs == 0 && cycle == f + 1);
            if (in_ready !== still_loading || out_valid !== expect_valid)
                $fatal(1, "CORE_PROTOCOL N=%0d frame=%0d cycle=%0d ready=%b valid=%b expected=%b/%b",
                       N, idx, cycle, in_ready, out_valid, still_loading, expect_valid);
            if (frame_done !== previous_done)
                $fatal(1, "CORE_PROTOCOL N=%0d frame_done on wrong edge", N);
            take = out_valid && out_ready;
            final_take = take && outputs == N-1;
            if (out_valid) begin
                if ({out_im, out_re} !== expected[outputs])
                    $fatal(1, "CORE_NUMERIC N=%0d frame=%0d bin=%0d actual=%08x expected=%08x",
                           N, idx, outputs, {out_im, out_re}, expected[outputs]);
                if (int'(out_bin_idx) != outputs || out_last !== (outputs == N-1))
                    $fatal(1, "CORE_PROTOCOL N=%0d frame=%0d index/last bin=%0d", N, idx, outputs);
                if (take) begin
                    if (outputs == 0) first = cycle - f;
                    if (kind == 1)
                        $display("CORE_BIN %0d %0d %08x", N, outputs, {out_im, out_re});
                    outputs++;
                    next_valid = cycle + 2;
                    stall_left = 2;
                end else stalled++;
            end else idle_payload();
            if (in_valid && in_ready) begin
                inputs++;
                if (inputs == N) begin
                    f = cycle;
                    next_valid = cycle + C + 2;
                end
            end
            #1;
            if (frame_done !== final_take || out_valid !==
                (!final_take && next_valid >= 0 && cycle + 1 >= next_valid))
                $fatal(1, "CORE_PROTOCOL N=%0d frame=%0d post-edge valid/done mismatch", N, idx);
        end
        if (stalled < 3 || first != C+5)
            $fatal(1, "CORE_PROTOCOL N=%0d first acceptance or stall witness missing", N);
        if (total > 32'hffff_ffff - 32'(clamps)) total = '1;
        else total += 32'(clamps);
        if (saturation_count !== total || overflow_flag !== (total != 0))
            $fatal(1, "CORE_NUMERIC N=%0d frame=%0d clamps=%0d expected=%0d overflow=%b",
                   N, idx, saturation_count, total, overflow_flag);
        completed++;
        f = cycle; // The following frame observes this completion pulse before the next edge.
        $display("CORE_FRAME %0d %0d %0d %0d %0d %0d", N, idx, kind, stalled, first, total);
    endtask

    initial begin
        int rc, size;
        if ($value$plusargs("size=%d", size) && N != size) begin
            finished = 1;
        end else begin
        if (!$value$plusargs("core=%s", base)) $fatal(1, "CORE_INPUT missing core stimulus");
        fd = $fopen($sformatf("%s%0d.txt", base, N), "r");
        if (!fd || $fscanf(fd, "%d", frame_count) != 1 || frame_count < 1)
            $fatal(1, "CORE_INPUT cannot read stimulus for N=%0d", N);
        reset_core();
        for (int idx = 0; idx < frame_count; idx++) begin
            rc = $fscanf(fd, "%d %d %d", kind, clamps, seed_count);
            if (rc != 3) $fatal(1, "CORE_INPUT frame header missing N=%0d frame=%0d", N, idx);
            for (int j = 0; j < N; j++)
                if ($fscanf(fd, "%h %h", samples[j], expected[j]) != 2)
                    $fatal(1, "CORE_INPUT truncated N=%0d frame=%0d bin=%0d", N, idx, j);
            if (idx == 0) begin
                abandon_frame(0);
                abandon_frame(1);
                abandon_frame(2);
            end
            if (seed_count != 0) begin
                // Preload only the initial count: natural rollover would need millions of frames.
                @(negedge clk);
                in_valid = 0;
                dut.g_legal.sat_count_reg = 32'(seed_count);
                total = 32'(seed_count);
            end
            run_frame(idx);
        end
        reset_core();
        $fclose(fd);
        $display("CORE_PASS %0d %0d %0d", N, completed, post_reset);
        finished = 1;
        end
    end
endmodule

module tb_billet_core;
    wire [7:0] finished;
    for (genvar k = 0; k < 8; k++) begin : sizes
        billet_core_case #(.N(2 << k)) witness (.finished(finished[k]));
    end
    initial begin
        wait (&finished);
        $finish;
    end
    initial #10000000 $fatal(1, "CORE_PROTOCOL test timeout");
endmodule

module tb_billet_illegal_n;
    billet_t1_top #(.N_POINTS(3)) dut (
        .clk(1'b0), .rst_n(1'b0), .in_valid(1'b0), .in_last(1'b0),
        .out_ready(1'b0), .in_re(16'b0), .in_im(16'b0)
    );
    initial #1 $fatal(1, "illegal N was not rejected by DUT");
endmodule

module tb_billet_illegal_log;
    billet_t1_top #(.N_POINTS(8), .LOG2_N(2)) dut (
        .clk(1'b0), .rst_n(1'b0), .in_valid(1'b0), .in_last(1'b0),
        .out_ready(1'b0), .in_re(16'b0), .in_im(16'b0)
    );
    initial #1 $fatal(1, "illegal LOG2_N was not rejected by DUT");
endmodule
