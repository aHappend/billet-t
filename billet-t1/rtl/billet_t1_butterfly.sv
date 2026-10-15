module billet_t1_butterfly (
    input  wire signed [15:0] a_re, a_im, b_re, b_im, w_re, w_im,
    output wire signed [15:0] y0_re, y0_im, y1_re, y1_im,
    output wire [2:0] sat_inc
);
    localparam integer SAMPLE_WIDTH = billet_t1_pkg::SAMPLE_WIDTH;
    localparam integer PRODUCT_WIDTH = billet_t1_pkg::PRODUCT_WIDTH;
    localparam integer COMPLEX_WIDTH = billet_t1_pkg::COMPLEX_WIDTH;
    localparam integer SUM_WIDTH = billet_t1_pkg::SUM_WIDTH;
    localparam integer FRACTION_BITS = billet_t1_pkg::FRACTION_BITS;
    localparam integer SAMPLE_MAX = billet_t1_pkg::SAMPLE_MAX;
    localparam integer SAMPLE_MIN = billet_t1_pkg::SAMPLE_MIN;

    wire signed [PRODUCT_WIDTH-1:0] rr = b_re * w_re;
    wire signed [PRODUCT_WIDTH-1:0] ii = b_im * w_im;
    wire signed [PRODUCT_WIDTH-1:0] ri = b_re * w_im;
    wire signed [PRODUCT_WIDTH-1:0] ir = b_im * w_re;
    wire signed [COMPLEX_WIDTH-1:0] p_re =
        $signed({rr[PRODUCT_WIDTH-1], rr}) - $signed({ii[PRODUCT_WIDTH-1], ii});
    wire signed [COMPLEX_WIDTH-1:0] p_im =
        $signed({ri[PRODUCT_WIDTH-1], ri}) + $signed({ir[PRODUCT_WIDTH-1], ir});
    wire signed [COMPLEX_WIDTH-1:0] t_re = p_re >>> FRACTION_BITS;
    wire signed [COMPLEX_WIDTH-1:0] t_im = p_im >>> FRACTION_BITS;
    wire signed [SUM_WIDTH-1:0] a_re_ext = {{(SUM_WIDTH-SAMPLE_WIDTH){a_re[15]}}, a_re};
    wire signed [SUM_WIDTH-1:0] a_im_ext = {{(SUM_WIDTH-SAMPLE_WIDTH){a_im[15]}}, a_im};
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

    wire clip_u_re = (u_re > SAMPLE_MAX) || (u_re < SAMPLE_MIN);
    wire clip_u_im = (u_im > SAMPLE_MAX) || (u_im < SAMPLE_MIN);
    wire clip_v_re = (v_re > SAMPLE_MAX) || (v_re < SAMPLE_MIN);
    wire clip_v_im = (v_im > SAMPLE_MAX) || (v_im < SAMPLE_MIN);
    assign y0_re = clamp16(u_re);
    assign y0_im = clamp16(u_im);
    assign y1_re = clamp16(v_re);
    assign y1_im = clamp16(v_im);
    assign sat_inc = {2'b00, clip_u_re} + {2'b00, clip_u_im}
                   + {2'b00, clip_v_re} + {2'b00, clip_v_im};
endmodule
