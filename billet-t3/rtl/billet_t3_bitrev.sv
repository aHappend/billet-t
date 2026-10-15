module billet_t3_bitrev (
    input wire [7:0] idx,
    input wire [3:0] log2_n,
    output reg [7:0] rev_idx
);
    integer b;
    always @* begin
        rev_idx = 8'd0;
        for (b = 0; b < 8; b = b + 1)
            if (b < log2_n)
                rev_idx[b] = idx[log2_n - 1 - b];
    end
endmodule
