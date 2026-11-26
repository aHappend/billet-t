module billet_t1_butterfly #(
    parameter integer RETIMED = 0
) (
    input  wire signed [15:0] a_re, a_im, b_re, b_im, w_re, w_im,
    output wire signed [15:0] y0_re, y0_im, y1_re, y1_im,
    output wire [2:0] sat_inc,
    input wire clk, prepare, compute
);
    localparam integer SAMPLE_WIDTH = billet_t1_pkg::SAMPLE_WIDTH;
    localparam integer PRODUCT_WIDTH = billet_t1_pkg::PRODUCT_WIDTH;
    localparam integer COMPLEX_WIDTH = billet_t1_pkg::COMPLEX_WIDTH;
    localparam integer SUM_WIDTH = billet_t1_pkg::SUM_WIDTH;
    localparam integer FRACTION_BITS = billet_t1_pkg::FRACTION_BITS;
    localparam signed [SUM_WIDTH-1:0] SAMPLE_MAX = SUM_WIDTH'(billet_t1_pkg::SAMPLE_MAX);
    localparam signed [SUM_WIDTH-1:0] SAMPLE_MIN = SUM_WIDTH'(billet_t1_pkg::SAMPLE_MIN);

    wire signed [15:0] mult_b_re, mult_b_im, mult_w_re, mult_w_im;
    wire signed [15:0] sum_a_re, sum_a_im;
    wire signed [COMPLEX_WIDTH-1:0] sum_p_re, sum_p_im;
    wire signed [PRODUCT_WIDTH-1:0] rr = mult_b_re * mult_w_re;
    wire signed [PRODUCT_WIDTH-1:0] ii = mult_b_im * mult_w_im;
    wire signed [PRODUCT_WIDTH-1:0] ri = mult_b_re * mult_w_im;
    wire signed [PRODUCT_WIDTH-1:0] ir = mult_b_im * mult_w_re;
    wire signed [COMPLEX_WIDTH-1:0] p_re =
        $signed({rr[PRODUCT_WIDTH-1], rr}) - $signed({ii[PRODUCT_WIDTH-1], ii});
    wire signed [COMPLEX_WIDTH-1:0] p_im =
        $signed({ri[PRODUCT_WIDTH-1], ri}) + $signed({ir[PRODUCT_WIDTH-1], ir});
    generate
        if (RETIMED == 1) begin : g_retimed
            reg signed [15:0] a_re_q, a_im_q, b_re_q, b_im_q, w_re_q, w_im_q;
            reg signed [15:0] aligned_a_re, aligned_a_im;
            reg signed [COMPLEX_WIDTH-1:0] p_re_q, p_im_q;
            // Payload is invalid until a fresh prepare followed by compute.
            always @(posedge clk) begin
                if (prepare) begin
                    a_re_q <= a_re;
                    a_im_q <= a_im;
                    b_re_q <= b_re;
                    b_im_q <= b_im;
                    w_re_q <= w_re;
                    w_im_q <= w_im;
                end
                if (compute) begin
                    p_re_q <= p_re;
                    p_im_q <= p_im;
                    aligned_a_re <= a_re_q;
                    aligned_a_im <= a_im_q;
                end
            end
            assign mult_b_re = b_re_q;
            assign mult_b_im = b_im_q;
            assign mult_w_re = w_re_q;
            assign mult_w_im = w_im_q;
            assign sum_a_re = aligned_a_re;
            assign sum_a_im = aligned_a_im;
            assign sum_p_re = p_re_q;
            assign sum_p_im = p_im_q;
        end else begin : g_combinational
            assign mult_b_re = b_re;
            assign mult_b_im = b_im;
            assign mult_w_re = w_re;
            assign mult_w_im = w_im;
            assign sum_a_re = a_re;
            assign sum_a_im = a_im;
            assign sum_p_re = p_re;
            assign sum_p_im = p_im;
        end
    endgenerate
    wire signed [COMPLEX_WIDTH-1:0] t_re = sum_p_re >>> FRACTION_BITS;
    wire signed [COMPLEX_WIDTH-1:0] t_im = sum_p_im >>> FRACTION_BITS;
    wire signed [SUM_WIDTH-1:0] a_re_ext = {{(SUM_WIDTH-SAMPLE_WIDTH){sum_a_re[15]}}, sum_a_re};
    wire signed [SUM_WIDTH-1:0] a_im_ext = {{(SUM_WIDTH-SAMPLE_WIDTH){sum_a_im[15]}}, sum_a_im};
    wire signed [SUM_WIDTH-1:0] t_re_ext = {t_re[COMPLEX_WIDTH-1], t_re};
    wire signed [SUM_WIDTH-1:0] t_im_ext = {t_im[COMPLEX_WIDTH-1], t_im};
    wire signed [SUM_WIDTH-1:0] u_re = (a_re_ext + t_re_ext) >>> 1;
    wire signed [SUM_WIDTH-1:0] u_im = (a_im_ext + t_im_ext) >>> 1;
    wire signed [SUM_WIDTH-1:0] v_re = (a_re_ext - t_re_ext) >>> 1;
    wire signed [SUM_WIDTH-1:0] v_im = (a_im_ext - t_im_ext) >>> 1;

    function automatic signed [15:0] clamp16(input signed [SUM_WIDTH-1:0] x);
        begin
            if (x > SAMPLE_MAX)
                clamp16 = 16'sh7fff;
            else if (x < SAMPLE_MIN)
                clamp16 = 16'sh8000;
            else
                clamp16 = x[15:0];
        end
    endfunction

    // A signed16 value has identical bits from the sign bit upward.
    wire clip_u_re = (|u_re[SUM_WIDTH-1:15]) && !(&u_re[SUM_WIDTH-1:15]);
    wire clip_u_im = (|u_im[SUM_WIDTH-1:15]) && !(&u_im[SUM_WIDTH-1:15]);
    wire clip_v_re = (|v_re[SUM_WIDTH-1:15]) && !(&v_re[SUM_WIDTH-1:15]);
    wire clip_v_im = (|v_im[SUM_WIDTH-1:15]) && !(&v_im[SUM_WIDTH-1:15]);
    wire [1:0] clips_u = {1'b0, clip_u_re} + {1'b0, clip_u_im};
    wire [1:0] clips_v = {1'b0, clip_v_re} + {1'b0, clip_v_im};
    assign y0_re = clamp16(u_re);
    assign y0_im = clamp16(u_im);
    assign y1_re = clamp16(v_re);
    assign y1_im = clamp16(v_im);
    assign sat_inc = {1'b0, clips_u} + {1'b0, clips_v};
endmodule
