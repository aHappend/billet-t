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
    genvar sat_candidate_index;

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
            // Only source-bank lookahead/FETCH reads are consumed.
            (* ramstyle = "M20K, no_rw_check", nomem2reg *) reg [31:0] bank0 [0:N_POINTS-1];
            (* ramstyle = "M20K, no_rw_check", nomem2reg *) reg [31:0] bank1 [0:N_POINTS-1];
            reg [31:0] bank0_a_q, bank0_b_q, bank1_a_q, bank1_b_q;
            wire [31:0] operand_a = src_bank ? bank1_a_q : bank0_a_q;
            wire [31:0] operand_b = src_bank ? bank1_b_q : bank0_b_q;
            reg [31:0] head_a, head_b;
            wire [A-1:0] next_a, next_b, next_k;
            reg [A-1:0] prepare_k;
            reg [A:0] next_stage_half;
            integer s;
            always @* begin
                next_stage_half = 0;
                for (s = 0; s < LOG2_N; s = s + 1) begin
                    if (stage_idx == S'(s)) begin
                        next_stage_half = (1 << (s + 1));
                    end
                end
            end
            wire last_butterfly = (addr_b == A'(N_POINTS-1));
            wire final_load = load_we && (load_addr == A'(N_POINTS-1));
            wire [31:0] committed_a = {y0_re, y0_im};
            wire [31:0] committed_b = {y1_re, y1_im};
            wire [31:0] next_head_a = (addr_a == 0) ? committed_a : head_a;
            wire [31:0] next_head_b = ({1'b0, addr_a} == next_stage_half) ? committed_a :
                         ({1'b0, addr_b} == next_stage_half) ? committed_b : head_b;
            wire [31:0] prepared_a = final_load ? head_a :
                         (last_butterfly ? next_head_a : operand_a);
            wire [31:0] prepared_b = final_load ?
                         ((N_POINTS == 2) ? {in_re, in_im} : head_b) :
                         (last_butterfly ? next_head_b : operand_b);
            reg [31:0] sat_count_reg;
            reg overflow_reg;
            reg [31:0] sat_candidates [1:4];
            // READ precedes every WRITE, with no intervening telemetry update.
            for (sat_candidate_index = 1; sat_candidate_index <= 4;
                 sat_candidate_index = sat_candidate_index + 1) begin : g_sat_candidate
                localparam [32:0] INCREMENT = sat_candidate_index;
                wire [32:0] candidate_sum = {1'b0, sat_count_reg} + INCREMENT;
                always @(posedge clk) begin
                    if (stage_read)
                        sat_candidates[sat_candidate_index] <= candidate_sum[32] ?
                            32'hffffffff : candidate_sum[31:0];
                end
            end
            wire [A-1:0] read_a_addr = (output_fetch || out_valid) ? output_addr : next_a;
            wire [A-1:0] bank0_a_addr = load_we ? reversed_addr :
                         ((stage_write && !dst_bank) ? addr_a : read_a_addr);
            wire [A-1:0] bank0_b_addr = (stage_write && !dst_bank) ? addr_b : next_b;
            wire [A-1:0] bank1_a_addr = (stage_write && dst_bank) ? addr_a : read_a_addr;
            wire [A-1:0] bank1_b_addr = (stage_write && dst_bank) ? addr_b : next_b;
            wire [31:0] bank0_write_data = load_we ? {in_re, in_im} : {y0_re, y0_im};

            billet_t1_buffer_sched #(.N_POINTS(N_POINTS)) buffer_sched (
                .clk(clk), .rst_n(rst_n), .in_valid(in_valid), .out_ready(out_ready),
                .in_ready(in_ready), .out_valid(out_valid), .out_last(out_last),
                .frame_done(frame_done), .load_we(load_we), .stage_read(stage_read),
                .stage_write(stage_write), .output_fetch(output_fetch),
                .src_bank(src_bank), .dst_bank(dst_bank), .load_addr(load_addr),
                .addr_a(addr_a), .addr_b(addr_b), .twiddle_addr(twiddle_addr),
                .output_addr(output_addr), .out_bin_idx(out_bin_idx),
                .stage_idx(stage_idx), .next_addr_a(next_a),
                .next_addr_b(next_b), .next_twiddle_addr(next_k)
            );
            billet_t1_bitrev #(.N_POINTS(N_POINTS)) bitrev (
                .idx(load_addr), .rev_idx(reversed_addr)
            );
            billet_t1_twiddle_rom #(.N_POINTS(N_POINTS)) twiddle_rom (
                .k(prepare_k), .w_re(w_re), .w_im(w_im)
            );
            billet_t1_butterfly #(.RETIMED(1)) butterfly (
                .a_re(prepared_a[31:16]), .a_im(prepared_a[15:0]),
                .b_re(prepared_b[31:16]), .b_im(prepared_b[15:0]),
                .w_re(w_re), .w_im(w_im), .y0_re(y0_re), .y0_im(y0_im),
                .y1_re(y1_re), .y1_im(y1_im), .sat_inc(sat_inc),
                .clk(clk), .prepare(stage_write || final_load), .compute(stage_read)
            );

            always @(posedge clk) begin
                if (stage_read)
                    prepare_k <= next_k;
                else
                    prepare_k <= 0;
            end

            always @(posedge clk) begin
                if (load_we || (stage_write && !dst_bank))
                    bank0[bank0_a_addr] <= bank0_write_data;
                bank0_a_q <= bank0[bank0_a_addr];
            end
            always @(posedge clk) begin
                if (stage_write && !dst_bank)
                    bank0[bank0_b_addr] <= {y1_re, y1_im};
                bank0_b_q <= bank0[bank0_b_addr];
            end
            always @(posedge clk) begin
                if (stage_write && dst_bank)
                    bank1[bank1_a_addr] <= {y0_re, y0_im};
                bank1_a_q <= bank1[bank1_a_addr];
            end
            always @(posedge clk) begin
                if (stage_write && dst_bank)
                    bank1[bank1_b_addr] <= {y1_re, y1_im};
                bank1_b_q <= bank1[bank1_b_addr];
            end

            always @(posedge clk) begin
                if (load_we) begin
                    if (reversed_addr == 0) head_a <= {in_re, in_im};
                    if (reversed_addr == 1) head_b <= {in_re, in_im};
                end else if (stage_write) begin
                    head_a <= next_head_a;
                    head_b <= next_head_b;
                end
            end

            always @(posedge clk or negedge rst_n) begin
                if (!rst_n) begin
                    sat_count_reg <= 0;
                    overflow_reg <= 0;
                end else begin
                    if (stage_write) begin
                        case (sat_inc)
                            3'd1: sat_count_reg <= sat_candidates[1];
                            3'd2: sat_count_reg <= sat_candidates[2];
                            3'd3: sat_count_reg <= sat_candidates[3];
                            3'd4: sat_count_reg <= sat_candidates[4];
                            default: ;
                        endcase
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
