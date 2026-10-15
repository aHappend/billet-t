module billet_t3_power_spectrum (
    input wire signed [15:0] in_re, in_im,
    output wire [31:0] out_power
);
    wire signed [31:0] square_re = in_re * in_re;
    wire signed [31:0] square_im = in_im * in_im;
    assign out_power = $unsigned(square_re) + $unsigned(square_im);
endmodule
