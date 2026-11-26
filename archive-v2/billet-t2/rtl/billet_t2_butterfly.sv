module billet_t2_butterfly (
    input wire signed [15:0] a_re, a_im, b_re, b_im,
    input wire signed [16:0] w_re, w_im,
    output wire signed [17:0] y0_re, y0_im, y1_re, y1_im
);
    wire signed [32:0] rr = b_re * w_re;
    wire signed [32:0] ii = b_im * w_im;
    wire signed [32:0] ri = b_re * w_im;
    wire signed [32:0] ir = b_im * w_re;
    wire signed [33:0] p_re = $signed({rr[32], rr}) - $signed({ii[32], ii});
    wire signed [33:0] p_im = $signed({ri[32], ri}) + $signed({ir[32], ir});
    wire signed [33:0] t_re = p_re >>> 15;
    wire signed [33:0] t_im = p_im >>> 15;
    wire signed [34:0] a_re_ext = {{19{a_re[15]}}, a_re};
    wire signed [34:0] a_im_ext = {{19{a_im[15]}}, a_im};
    wire signed [34:0] t_re_ext = {t_re[33], t_re};
    wire signed [34:0] t_im_ext = {t_im[33], t_im};
    wire signed [34:0] u_re = a_re_ext + t_re_ext;
    wire signed [34:0] u_im = a_im_ext + t_im_ext;
    wire signed [34:0] v_re = a_re_ext - t_re_ext;
    wire signed [34:0] v_im = a_im_ext - t_im_ext;

    assign y0_re = u_re[17:0];
    assign y0_im = u_im[17:0];
    assign y1_re = v_re[17:0];
    assign y1_im = v_im[17:0];
endmodule
