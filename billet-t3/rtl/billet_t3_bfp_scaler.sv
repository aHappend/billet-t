module billet_t3_bfp_scaler (
    input wire clk, rst_n,
    input wire frame_start, stage_start, observe_valid, stage_commit,
    input wire [1:0] scale_mode,
    input wire stage_shift_bit,
    input wire signed [17:0] raw0_re, raw0_im, raw1_re, raw1_im,
    input wire signed [17:0] norm_re, norm_im,
    output wire signed [15:0] scaled_re, scaled_im,
    output wire [1:0] sat_inc,
    output wire [3:0] block_exp,
    output wire stage_shift
);
    reg headroom_needed;
    reg [3:0] exponent;

    function automatic outside16(input signed [17:0] x);
        begin
            outside16 = (x > 18'sd32767) || (x < -18'sd32768);
        end
    endfunction

    function automatic signed [15:0] clamp16(input signed [17:0] x);
        begin
            if (x > 18'sd32767)
                clamp16 = 16'sh7fff;
            else if (x < -18'sd32768)
                clamp16 = 16'sh8000;
            else
                clamp16 = x[15:0];
        end
    endfunction

    wire observed_overflow = outside16(raw0_re) || outside16(raw0_im)
                           || outside16(raw1_re) || outside16(raw1_im);
    assign stage_shift = rst_n && ((scale_mode == 2'd0)
                       || ((scale_mode == 2'd1) && stage_shift_bit)
                       || ((scale_mode == 2'd2) && headroom_needed));
    wire signed [17:0] shifted_re = norm_re >>> stage_shift;
    wire signed [17:0] shifted_im = norm_im >>> stage_shift;
    assign scaled_re = rst_n ? clamp16(shifted_re) : 16'sd0;
    assign scaled_im = rst_n ? clamp16(shifted_im) : 16'sd0;
    assign sat_inc = rst_n ? ({1'b0, outside16(shifted_re)}
                           + {1'b0, outside16(shifted_im)}) : 2'd0;
    assign block_exp = rst_n ? exponent : 4'd0;

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            headroom_needed <= 1'b0;
            exponent <= 4'd0;
        end else begin
            if (frame_start || stage_start)
                headroom_needed <= 1'b0;
            else if (observe_valid)
                headroom_needed <= headroom_needed || observed_overflow;

            if (frame_start)
                exponent <= 4'd0;
            else if (stage_commit)
                exponent <= exponent + {3'd0, stage_shift};
        end
    end
endmodule
