module billet_t1_top #(
    parameter integer N_POINTS = 256,
    parameter integer LOG2_N = (N_POINTS > 1) ? $clog2(N_POINTS) : 1
) (
    input wire clk, rst_n, in_valid, in_last, out_ready,
    input wire signed [15:0] in_re, in_im,
    output wire in_ready, out_valid, out_last, frame_done, overflow_flag,
    output wire signed [15:0] out_re, out_im,
    output wire [((LOG2_N > 0) ? LOG2_N : 1)-1:0] out_bin_idx,
    output wire [31:0] saturation_count
);
    localparam integer A = (LOG2_N > 0) ? LOG2_N : 1;
    localparam integer S = (LOG2_N > 1) ? $clog2(LOG2_N) : 1;

    generate
        if ((N_POINTS >= 2) && (N_POINTS <= 256) &&
            ((N_POINTS & (N_POINTS-1)) == 0) &&
            (LOG2_N == $clog2(N_POINTS))) begin : g_legal
            wire load_we, stage_read, stage_write, output_fetch;
            wire src_bank, dst_bank;
            wire [A-1:0] load_addr, reversed_addr, addr_a, addr_b;
            wire [A-1:0] twiddle_addr, output_addr;
            wire [S-1:0] stage_idx;
            wire signed [15:0] w_re, w_im;
            wire signed [15:0] y0_re, y0_im, y1_re, y1_im;
            wire [2:0] sat_inc;
            reg [31:0] bank0 [0:N_POINTS-1];
            reg [31:0] bank1 [0:N_POINTS-1];
            reg [31:0] operand_a, operand_b;
            reg [31:0] sat_count_reg;
            reg overflow_reg;
            wire [32:0] sat_sum = {1'b0, sat_count_reg} + {30'b0, sat_inc};
            wire [A-1:0] port_a_read_addr = output_fetch ? output_addr : addr_a;
            wire [A-1:0] bank0_write_addr = load_we ? reversed_addr : addr_a;
            wire [31:0] bank0_write_data = load_we ? {in_re, in_im} : {y0_re, y0_im};

            billet_t1_buffer_sched #(.N_POINTS(N_POINTS)) buffer_sched (
                .clk(clk), .rst_n(rst_n), .in_valid(in_valid), .out_ready(out_ready),
                .in_ready(in_ready), .out_valid(out_valid), .out_last(out_last),
                .frame_done(frame_done), .load_we(load_we), .stage_read(stage_read),
                .stage_write(stage_write), .output_fetch(output_fetch),
                .src_bank(src_bank), .dst_bank(dst_bank), .load_addr(load_addr),
                .addr_a(addr_a), .addr_b(addr_b), .twiddle_addr(twiddle_addr),
                .output_addr(output_addr), .out_bin_idx(out_bin_idx),
                .stage_idx(stage_idx)
            );
            billet_t1_bitrev #(.N_POINTS(N_POINTS)) bitrev (
                .idx(load_addr), .rev_idx(reversed_addr)
            );
            billet_t1_twiddle_rom #(.N_POINTS(N_POINTS)) twiddle_rom (
                .k(twiddle_addr), .w_re(w_re), .w_im(w_im)
            );
            billet_t1_butterfly butterfly (
                .a_re(operand_a[31:16]), .a_im(operand_a[15:0]),
                .b_re(operand_b[31:16]), .b_im(operand_b[15:0]),
                .w_re(w_re), .w_im(w_im), .y0_re(y0_re), .y0_im(y0_im),
                .y1_re(y1_re), .y1_im(y1_im), .sat_inc(sat_inc)
            );

            always @(posedge clk) begin
                if (load_we || (stage_write && !dst_bank))
                    bank0[bank0_write_addr] <= bank0_write_data;
                if (stage_write && !dst_bank)
                    bank0[addr_b] <= {y1_re, y1_im};
                if (stage_write && dst_bank) begin
                    bank1[addr_a] <= {y0_re, y0_im};
                    bank1[addr_b] <= {y1_re, y1_im};
                end
            end

            always @(posedge clk or negedge rst_n) begin
                if (!rst_n) begin
                    operand_a <= 0;
                    operand_b <= 0;
                    sat_count_reg <= 0;
                    overflow_reg <= 0;
                end else begin
                    if (stage_read || output_fetch) begin
                        if (src_bank)
                            operand_a <= bank1[port_a_read_addr];
                        else
                            operand_a <= bank0[port_a_read_addr];
                    end
                    if (stage_read) begin
                        if (src_bank)
                            operand_b <= bank1[addr_b];
                        else
                            operand_b <= bank0[addr_b];
                    end
                    if (stage_write) begin
                        if (sat_sum[32])
                            sat_count_reg <= 32'hffffffff;
                        else
                            sat_count_reg <= sat_sum[31:0];
                        if (sat_inc != 0)
                            overflow_reg <= 1'b1;
                    end
                end
            end

            assign out_re = out_valid ? operand_a[31:16] : 16'sd0;
            assign out_im = out_valid ? operand_a[15:0] : 16'sd0;
            assign saturation_count = rst_n ? sat_count_reg : 32'b0;
            assign overflow_flag = rst_n && overflow_reg;
        end else begin : g_illegal
            assign {in_ready,out_valid,out_last,frame_done,overflow_flag} = 5'b0;
            assign out_re = 0;
            assign out_im = 0;
            assign out_bin_idx = 0;
            assign saturation_count = 0;
            initial $fatal(1, "PARAMETER ERROR: billet_t1_top requires power-of-two N_POINTS in [2,256] and LOG2_N=$clog2(N_POINTS)");
        end
    endgenerate
endmodule
