module billet_t3_fft_core (
    input wire clk, rst_n, in_valid, in_last, out_ready,
    input wire signed [15:0] in_re, in_im,
    input wire [3:0] cfg_log2_n,
    input wire cfg_ifft,
    input wire [1:0] cfg_scale_mode,
    input wire [7:0] cfg_stage_shift_mask,
    output wire in_ready, out_valid, out_last, frame_done,
    output wire overflow_flag, cfg_error,
    output wire signed [15:0] out_re, out_im,
    output wire [7:0] out_bin_idx,
    output wire [3:0] out_block_exp,
    output wire [31:0] saturation_count
);
    localparam [2:0] LOAD = 3'd0, BUTTERFLY_READ = 3'd1,
                     BUTTERFLY_WRITE = 3'd2, NORMALIZE_READ = 3'd3,
                     NORMALIZE_WRITE = 3'd4, OUTPUT_FETCH = 3'd5,
                     OUTPUT_SEND = 3'd6;
    reg [2:0] state;
    reg active;
    reg [3:0] log2_n;
    reg ifft;
    reg [1:0] scale_mode;
    reg [7:0] shift_mask;
    reg [8:0] n_points;
    reg [7:0] load_count, butterfly_count, norm_count, output_count;
    reg [2:0] stage_count;
    reg [31:0] operand_a, operand_b;
    reg [35:0] norm_operand;
    reg [31:0] sat_count;
    reg overflow_reg, done_reg;
    reg [31:0] sample_bank [0:255];
    reg [35:0] raw_bank [0:255];

    wire config_valid = (cfg_log2_n >= 4'd4) && (cfg_log2_n <= 4'd8)
                      && (cfg_scale_mode != 2'd3);
    assign in_ready = rst_n && (state == LOAD) && (active || config_valid);
    assign cfg_error = rst_n && (state == LOAD) && !active && !config_valid;
    wire load_we = in_valid && in_ready;
    wire frame_start = load_we && !active;
    wire last_load = ({1'b0, load_count} == n_points - 9'd1);
    wire final_stage = ({1'b0, stage_count} == log2_n - 4'd1);
    wire final_norm = ({1'b0, norm_count} == n_points - 9'd1);
    wire normalize_write = rst_n && (state == NORMALIZE_WRITE);
    wire stage_commit = normalize_write && final_norm;
    wire stage_start = (load_we && active && last_load)
                     || (stage_commit && !final_stage);
    wire observe_valid = rst_n && (state == BUTTERFLY_WRITE);
    wire [7:0] reversed_addr;
    wire [3:0] load_log2_n = active ? log2_n : cfg_log2_n;
    wire [8:0] half_span = 9'd1 << stage_count;
    wire [8:0] j = {1'b0, butterfly_count} & (half_span - 9'd1);
    wire [8:0] base_addr =
        ({1'b0, butterfly_count} >> stage_count) << (stage_count + 4'd1);
    wire [8:0] a_addr = base_addr + j;
    wire [8:0] b_addr = a_addr + half_span;
    wire [8:0] twiddle_addr = j << (4'd7 - {1'b0, stage_count});
    wire signed [16:0] w_re, w_im;
    wire signed [17:0] y0_re, y0_im, y1_re, y1_im;
    wire signed [15:0] scaled_re, scaled_im;
    wire [1:0] sat_inc;
    wire [3:0] block_exp;
    wire stage_shift;
    wire [32:0] sat_sum = {1'b0, sat_count} + {31'd0, sat_inc};

    billet_t3_bitrev bitrev (
        .idx(load_count), .log2_n(load_log2_n), .rev_idx(reversed_addr)
    );
    billet_t3_twiddle_rom twiddle_rom (
        .k(twiddle_addr[6:0]), .ifft(ifft), .w_re(w_re), .w_im(w_im)
    );
    billet_t3_butterfly butterfly (
        .a_re(operand_a[31:16]), .a_im(operand_a[15:0]),
        .b_re(operand_b[31:16]), .b_im(operand_b[15:0]),
        .w_re(w_re), .w_im(w_im),
        .y0_re(y0_re), .y0_im(y0_im), .y1_re(y1_re), .y1_im(y1_im)
    );
    billet_t3_bfp_scaler bfp_scaler (
        .clk(clk), .rst_n(rst_n), .frame_start(frame_start),
        .stage_start(stage_start), .observe_valid(observe_valid),
        .stage_commit(stage_commit), .scale_mode(scale_mode),
        .stage_shift_bit(shift_mask[stage_count]),
        .raw0_re(y0_re), .raw0_im(y0_im), .raw1_re(y1_re), .raw1_im(y1_im),
        .norm_re(norm_operand[35:18]), .norm_im(norm_operand[17:0]),
        .scaled_re(scaled_re), .scaled_im(scaled_im),
        .sat_inc(sat_inc), .block_exp(block_exp), .stage_shift(stage_shift)
    );

    always @(posedge clk) begin
        if (rst_n) begin
            if (load_we)
                sample_bank[reversed_addr] <= {in_re, in_im};
            if (observe_valid) begin
                raw_bank[a_addr[7:0]] <= {y0_re, y0_im};
                raw_bank[b_addr[7:0]] <= {y1_re, y1_im};
            end
            if (normalize_write)
                sample_bank[norm_count] <= {scaled_re, scaled_im};
        end
    end

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            state <= LOAD;
            active <= 1'b0;
            log2_n <= 4'd0;
            ifft <= 1'b0;
            scale_mode <= 2'd0;
            shift_mask <= 8'd0;
            n_points <= 9'd0;
            load_count <= 8'd0;
            butterfly_count <= 8'd0;
            norm_count <= 8'd0;
            output_count <= 8'd0;
            stage_count <= 3'd0;
            operand_a <= 32'd0;
            operand_b <= 32'd0;
            norm_operand <= 36'd0;
            sat_count <= 32'd0;
            overflow_reg <= 1'b0;
            done_reg <= 1'b0;
        end else begin
            done_reg <= 1'b0;
            if (normalize_write) begin
                if (sat_sum[32])
                    sat_count <= 32'hffffffff;
                else
                    sat_count <= sat_sum[31:0];
                if (sat_inc != 2'd0)
                    overflow_reg <= 1'b1;
            end
            case (state)
                LOAD: if (load_we) begin
                    if (!active) begin
                        active <= 1'b1;
                        log2_n <= cfg_log2_n;
                        ifft <= cfg_ifft;
                        scale_mode <= cfg_scale_mode;
                        shift_mask <= cfg_stage_shift_mask;
                        n_points <= 9'd1 << cfg_log2_n;
                        load_count <= 8'd1;
                    end else if (last_load) begin
                        load_count <= 8'd0;
                        butterfly_count <= 8'd0;
                        stage_count <= 3'd0;
                        state <= BUTTERFLY_READ;
                    end else
                        load_count <= load_count + 8'd1;
                end
                BUTTERFLY_READ: begin
                    operand_a <= sample_bank[a_addr[7:0]];
                    operand_b <= sample_bank[b_addr[7:0]];
                    state <= BUTTERFLY_WRITE;
                end
                BUTTERFLY_WRITE: begin
                    if ({1'b0, butterfly_count} == (n_points >> 1) - 9'd1) begin
                        butterfly_count <= 8'd0;
                        norm_count <= 8'd0;
                        state <= NORMALIZE_READ;
                    end else begin
                        butterfly_count <= butterfly_count + 8'd1;
                        state <= BUTTERFLY_READ;
                    end
                end
                NORMALIZE_READ: begin
                    norm_operand <= raw_bank[norm_count];
                    state <= NORMALIZE_WRITE;
                end
                NORMALIZE_WRITE: begin
                    if (final_norm) begin
                        norm_count <= 8'd0;
                        if (final_stage) begin
                            output_count <= 8'd0;
                            state <= OUTPUT_FETCH;
                        end else begin
                            stage_count <= stage_count + 3'd1;
                            state <= BUTTERFLY_READ;
                        end
                    end else begin
                        norm_count <= norm_count + 8'd1;
                        state <= NORMALIZE_READ;
                    end
                end
                OUTPUT_FETCH: begin
                    operand_a <= sample_bank[output_count];
                    state <= OUTPUT_SEND;
                end
                OUTPUT_SEND: if (out_ready) begin
                    if ({1'b0, output_count} == n_points - 9'd1) begin
                        output_count <= 8'd0;
                        active <= 1'b0;
                        done_reg <= 1'b1;
                        state <= LOAD;
                    end else begin
                        output_count <= output_count + 8'd1;
                        state <= OUTPUT_FETCH;
                    end
                end
                default: begin
                    state <= LOAD;
                    active <= 1'b0;
                    load_count <= 8'd0;
                    butterfly_count <= 8'd0;
                    norm_count <= 8'd0;
                    output_count <= 8'd0;
                    stage_count <= 3'd0;
                end
            endcase
        end
    end

    assign out_valid = rst_n && (state == OUTPUT_SEND);
    assign out_last = out_valid && ({1'b0, output_count} == n_points - 9'd1);
    assign out_re = out_valid ? $signed(operand_a[31:16]) : 16'sd0;
    assign out_im = out_valid ? $signed(operand_a[15:0]) : 16'sd0;
    assign out_bin_idx = out_valid ? output_count : 8'd0;
    assign out_block_exp = out_valid ? block_exp : 4'd0;
    assign frame_done = rst_n && done_reg;
    assign saturation_count = rst_n ? sat_count : 32'd0;
    assign overflow_flag = rst_n && overflow_reg;
endmodule
