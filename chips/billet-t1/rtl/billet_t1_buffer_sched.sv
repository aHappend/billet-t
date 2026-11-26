module billet_t1_buffer_sched #(
    parameter integer N_POINTS = 256,
    parameter integer LOG2_N = (N_POINTS > 1) ? $clog2(N_POINTS) : 1,
    parameter integer A = (LOG2_N > 0) ? LOG2_N : 1,
    parameter integer S = (LOG2_N > 1) ? $clog2(LOG2_N) : 1
) (
    input wire clk, rst_n, in_valid, out_ready,
    output wire in_ready, out_valid, out_last, frame_done,
    output wire load_we, stage_read, stage_write, output_fetch,
    output wire src_bank, dst_bank,
    output wire [A-1:0] load_addr, addr_a, addr_b, twiddle_addr,
    output wire [A-1:0] output_addr, out_bin_idx,
    output wire [S-1:0] stage_idx,
    output wire [A-1:0] next_addr_a, next_addr_b, next_twiddle_addr
);
    generate
        if ((N_POINTS >= 2) && (N_POINTS <= 256) &&
            ((N_POINTS & (N_POINTS-1)) == 0) &&
            (LOG2_N == $clog2(N_POINTS)) && (A == LOG2_N) &&
            (S == ((LOG2_N > 1) ? $clog2(LOG2_N) : 1))) begin : g_legal
            localparam [2:0] LOAD=3'd0, READ=3'd1, WRITE=3'd2,
                             FETCH=3'd3, SEND=3'd4;
            localparam [A-1:0] LAST_SAMPLE = A'(N_POINTS - 1);
            localparam [A-1:0] LAST_BUTTERFLY = A'(N_POINTS/2 - 1);
            localparam [S-1:0] LAST_STAGE = S'(LOG2_N - 1);
            reg [2:0] state;
            reg [A-1:0] load_count, butterfly_count, output_count;
            reg [S-1:0] stage_count;
            reg source_bank, done_reg;
            reg [A-1:0] a_addr, b_addr, k_addr;
            wire [A-1:0] next_count = butterfly_count + 1'b1;
            reg [A-1:0] next_a, next_b, next_k;
            integer s;
            always @* begin
                a_addr = 0;
                b_addr = 0;
                k_addr = 0;
                next_a = 0;
                next_b = 0;
                next_k = 0;
                for (s = 0; s < LOG2_N; s = s + 1) begin
                    if (stage_count == S'(s)) begin
                        a_addr = ((butterfly_count >> s) << (s + 1)) |
                                 (butterfly_count & ((1 << s) - 1));
                        b_addr = a_addr | (1 << s);
                        k_addr = (butterfly_count & ((1 << s) - 1)) <<
                                 (LOG2_N - s - 1);
                        next_a = ((next_count >> s) << (s + 1)) |
                                 (next_count & ((1 << s) - 1));
                        next_b = next_a | (1 << s);
                        next_k = (next_count & ((1 << s) - 1)) <<
                                 (LOG2_N - s - 1);
                    end
                end
            end

            assign in_ready = rst_n && (state == LOAD);
            assign out_valid = rst_n && (state == SEND);
            assign out_last = out_valid && (output_count == LAST_SAMPLE);
            assign frame_done = rst_n && done_reg;
            assign load_we = in_valid && in_ready;
            assign stage_read = rst_n && (state == READ);
            assign stage_write = rst_n && (state == WRITE);
            assign output_fetch = rst_n && (state == FETCH);
            assign src_bank = rst_n && source_bank;
            assign dst_bank = rst_n && !source_bank;
            assign load_addr = rst_n ? load_count : {A{1'b0}};
            assign addr_a = rst_n ? a_addr[A-1:0] : {A{1'b0}};
            assign addr_b = rst_n ? b_addr[A-1:0] : {A{1'b0}};
            assign twiddle_addr = rst_n ? k_addr[A-1:0] : {A{1'b0}};
            assign output_addr = rst_n ? output_count : {A{1'b0}};
            assign out_bin_idx = out_valid ? output_count : {A{1'b0}};
            assign stage_idx = rst_n ? stage_count : {S{1'b0}};
            assign next_addr_a = rst_n ? next_a : {A{1'b0}};
            assign next_addr_b = rst_n ? next_b : {A{1'b0}};
            assign next_twiddle_addr = rst_n ? next_k : {A{1'b0}};

            always @(posedge clk or negedge rst_n) begin
                if (!rst_n) begin
                    state <= LOAD;
                    load_count <= 0;
                    butterfly_count <= 0;
                    output_count <= 0;
                    stage_count <= 0;
                    source_bank <= 0;
                    done_reg <= 0;
                end else begin
                    done_reg <= 0;
                    case (state)
                        LOAD: if (in_valid) begin
                            if (load_count == LAST_SAMPLE) begin
                                load_count <= 0;
                                butterfly_count <= 0;
                                stage_count <= 0;
                                source_bank <= 0;
                                state <= READ;
                            end else
                                load_count <= load_count + 1'b1;
                        end
                        READ: state <= WRITE;
                        WRITE: begin
                            if (butterfly_count == LAST_BUTTERFLY) begin
                                butterfly_count <= 0;
                                source_bank <= !source_bank;
                                if (stage_count == LAST_STAGE) begin
                                    output_count <= 0;
                                    state <= FETCH;
                                end else begin
                                    stage_count <= stage_count + 1'b1;
                                    state <= READ;
                                end
                            end else begin
                                butterfly_count <= butterfly_count + 1'b1;
                                state <= READ;
                            end
                        end
                        FETCH: state <= SEND;
                        SEND: if (out_ready) begin
                            if (output_count == LAST_SAMPLE) begin
                                output_count <= 0;
                                done_reg <= 1;
                                state <= LOAD;
                            end else begin
                                output_count <= output_count + 1'b1;
                                state <= FETCH;
                            end
                        end
                        default: begin
                            state <= LOAD;
                            load_count <= 0;
                            butterfly_count <= 0;
                            output_count <= 0;
                            stage_count <= 0;
                            source_bank <= 0;
                        end
                    endcase
                end
            end
        end else begin : g_illegal
            assign {in_ready,out_valid,out_last,frame_done,load_we,
                    stage_read,stage_write,output_fetch,src_bank,dst_bank} = 10'b0;
            assign load_addr = 0;
            assign addr_a = 0;
            assign addr_b = 0;
            assign twiddle_addr = 0;
            assign output_addr = 0;
            assign out_bin_idx = 0;
            assign stage_idx = 0;
            assign next_addr_a = 0;
            assign next_addr_b = 0;
            assign next_twiddle_addr = 0;
            initial $fatal(1, "PARAMETER ERROR: billet_t1_buffer_sched requires power-of-two N_POINTS in [2,256] and derived widths");
        end
    endgenerate
endmodule
