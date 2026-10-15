module billet_t1_bitrev #(
    parameter integer N_POINTS = 256,
    parameter integer LOG2_N = (N_POINTS > 1) ? $clog2(N_POINTS) : 1,
    parameter integer A = (LOG2_N > 0) ? LOG2_N : 1
) (
    input  wire [A-1:0] idx,
    output wire [A-1:0] rev_idx
);
    generate
        if ((N_POINTS >= 2) && (N_POINTS <= 256) &&
            ((N_POINTS & (N_POINTS-1)) == 0) &&
            (LOG2_N == $clog2(N_POINTS)) && (A == LOG2_N)) begin : g_legal
            for (genvar b = 0; b < A; b = b + 1) begin : g_bit
                assign rev_idx[b] = idx[LOG2_N-1-b];
            end
        end else begin : g_illegal
            assign rev_idx = {A{1'b0}};
            initial $fatal(1, "PARAMETER ERROR: billet_t1_bitrev requires power-of-two N_POINTS in [2,256] and derived widths");
        end
    endgenerate
endmodule
