module billet_t3_top (
    input wire clk, rst_n, in_valid, in_last, out_ready,
    input wire signed [15:0] in_re, in_im,
    input wire [1:0] ch_id,
    input wire [3:0] cfg_log2_n,
    input wire cfg_ifft,
    input wire [1:0] cfg_scale_mode,
    input wire [7:0] cfg_stage_shift_mask,
    input wire cfg_overlap_mode,
    input wire [1:0] cfg_window_mode,
    output wire in_ready, out_valid, out_last, frame_done,
    output wire overflow_flag, cfg_error,
    output wire signed [15:0] out_re, out_im,
    output wire [31:0] out_power, saturation_count,
    output wire [7:0] out_bin_idx,
    output wire [3:0] out_block_exp,
    output wire [1:0] out_ch_id, frame_done_ch_id
);
    wire f_ready, f_valid, f_last;
    wire signed [15:0] f_re, f_im, windowed_re, windowed_im;
    wire [7:0] f_idx;
    wire [1:0] f_ch_id;
    wire [3:0] f_log2_n;
    wire f_ifft;
    wire [1:0] f_scale_mode;
    wire [7:0] f_stage_shift_mask;
    wire f_overlap_mode;
    wire [1:0] f_window_mode;
    wire core_cfg_error;
    reg [1:0] active_ch, done_ch;

    billet_t3_channel_buf channel_buf (
        .clk(clk), .rst_n(rst_n), .in_valid(in_valid), .in_last(in_last),
        .in_re(in_re), .in_im(in_im), .ch_id(ch_id),
        .cfg_log2_n(cfg_log2_n), .cfg_ifft(cfg_ifft),
        .cfg_scale_mode(cfg_scale_mode), .cfg_stage_shift_mask(cfg_stage_shift_mask),
        .cfg_overlap_mode(cfg_overlap_mode), .cfg_window_mode(cfg_window_mode),
        .in_ready(in_ready), .cfg_error(cfg_error),
        .f_ready(f_ready), .f_valid(f_valid), .f_last(f_last),
        .f_re(f_re), .f_im(f_im), .f_idx(f_idx), .f_ch_id(f_ch_id),
        .f_log2_n(f_log2_n), .f_ifft(f_ifft), .f_scale_mode(f_scale_mode),
        .f_stage_shift_mask(f_stage_shift_mask),
        .f_overlap_mode(f_overlap_mode), .f_window_mode(f_window_mode)
    );

    billet_t3_window window (
        .in_re(f_re), .in_im(f_im), .sample_idx(f_idx),
        .log2_n(f_log2_n), .window_mode(f_window_mode),
        .out_re(windowed_re), .out_im(windowed_im)
    );

    billet_t3_fft_core fft_core (
        .clk(clk), .rst_n(rst_n), .in_valid(f_valid), .in_last(f_last),
        .in_re(windowed_re), .in_im(windowed_im),
        .cfg_log2_n(f_log2_n), .cfg_ifft(f_ifft),
        .cfg_scale_mode(f_scale_mode), .cfg_stage_shift_mask(f_stage_shift_mask),
        .in_ready(f_ready), .cfg_error(core_cfg_error),
        .out_ready(out_ready), .out_valid(out_valid), .out_last(out_last),
        .out_re(out_re), .out_im(out_im), .out_bin_idx(out_bin_idx),
        .out_block_exp(out_block_exp), .frame_done(frame_done),
        .overflow_flag(overflow_flag), .saturation_count(saturation_count)
    );

    billet_t3_power_spectrum power_spectrum (
        .in_re(out_re), .in_im(out_im), .out_power(out_power)
    );

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            active_ch <= 2'd0;
            done_ch <= 2'd0;
        end else begin
            if (f_valid && f_ready && (f_idx == 8'd0))
                active_ch <= f_ch_id;
            if (out_valid && out_ready && out_last)
                done_ch <= active_ch;
        end
    end

    assign out_ch_id = out_valid ? active_ch : 2'd0;
    assign frame_done_ch_id = frame_done ? done_ch : 2'd0;
endmodule
