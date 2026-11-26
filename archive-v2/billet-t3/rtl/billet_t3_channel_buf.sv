module billet_t3_channel_buf (
    input wire clk, rst_n, in_valid, in_last,
    input wire signed [15:0] in_re, in_im,
    input wire [1:0] ch_id,
    input wire [3:0] cfg_log2_n,
    input wire cfg_ifft,
    input wire [1:0] cfg_scale_mode,
    input wire [7:0] cfg_stage_shift_mask,
    input wire cfg_overlap_mode,
    input wire [1:0] cfg_window_mode,
    input wire f_ready,
    output wire in_ready, cfg_error, f_valid, f_last,
    output wire signed [15:0] f_re, f_im,
    output wire [7:0] f_idx,
    output wire [1:0] f_ch_id,
    output wire [3:0] f_log2_n,
    output wire f_ifft,
    output wire [1:0] f_scale_mode,
    output wire [7:0] f_stage_shift_mask,
    output wire f_overlap_mode,
    output wire [1:0] f_window_mode
);
    reg [31:0] sample_ring [0:1023];
    reg [3:0] epoch_valid, pending;
    reg [3:0] log2_n [0:3];
    reg ifft [0:3];
    reg [1:0] scale_mode [0:3];
    reg [7:0] shift_mask [0:3];
    reg overlap_mode [0:3];
    reg [1:0] window_mode [0:3];
    reg [8:0] fill_count [0:3];
    reg [7:0] write_ptr [0:3];
    reg [7:0] frame_base [0:3];
    reg selected;
    reg [1:0] selected_ch, priority_ch;
    reg [7:0] transfer_idx;

    wire config_valid = (cfg_log2_n >= 4'd4) && (cfg_log2_n <= 4'd8)
                      && (cfg_scale_mode != 2'd3)
                      && (cfg_window_mode != 2'd3);
    wire [3:0] input_log2_n = epoch_valid[ch_id] ? log2_n[ch_id] : cfg_log2_n;
    wire input_overlap = epoch_valid[ch_id] ? overlap_mode[ch_id] : cfg_overlap_mode;
    wire [8:0] input_n = 9'd1 << input_log2_n;
    wire [7:0] next_write_ptr =
        ({1'b0, write_ptr[ch_id]} == input_n - 9'd1)
        ? 8'd0 : write_ptr[ch_id] + 8'd1;
    assign cfg_error = rst_n && !epoch_valid[ch_id] && !config_valid;
    assign in_ready = rst_n && !pending[ch_id]
                    && (epoch_valid[ch_id] || config_valid);
    wire input_accept = in_valid && in_ready;

    reg found;
    reg [1:0] chosen_ch;
    reg [1:0] candidate;
    integer offset;
    always @* begin
        found = 1'b0;
        chosen_ch = 2'd0;
        candidate = 2'd0;
        for (offset = 0; offset < 4; offset = offset + 1) begin
            candidate = priority_ch + offset[1:0];
            if (!found && pending[candidate]) begin
                found = 1'b1;
                chosen_ch = candidate;
            end
        end
    end

    wire [8:0] selected_n = 9'd1 << log2_n[selected_ch];
    wire [8:0] frame_address_sum = {1'b0, frame_base[selected_ch]}
                                 + {1'b0, transfer_idx};
    wire [8:0] frame_address = frame_address_sum & (selected_n - 9'd1);
    assign f_valid = rst_n && selected;
    wire [31:0] frame_sample = f_valid
        ? sample_ring[{selected_ch, frame_address[7:0]}] : 32'd0;
    assign f_last = f_valid && ({1'b0, transfer_idx} == selected_n - 9'd1);
    assign f_re = f_valid ? $signed(frame_sample[31:16]) : 16'sd0;
    assign f_im = f_valid ? $signed(frame_sample[15:0]) : 16'sd0;
    assign f_idx = f_valid ? transfer_idx : 8'd0;
    assign f_ch_id = f_valid ? selected_ch : 2'd0;
    assign f_log2_n = f_valid ? log2_n[selected_ch] : 4'd0;
    assign f_ifft = f_valid && ifft[selected_ch];
    assign f_scale_mode = f_valid ? scale_mode[selected_ch] : 2'd0;
    assign f_stage_shift_mask = f_valid ? shift_mask[selected_ch] : 8'd0;
    assign f_overlap_mode = f_valid && overlap_mode[selected_ch];
    assign f_window_mode = f_valid ? window_mode[selected_ch] : 2'd0;

    always @(posedge clk) begin
        if (input_accept)
            sample_ring[{ch_id, write_ptr[ch_id]}] <= {in_re, in_im};
    end

    integer ch;
    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            epoch_valid <= 4'd0;
            pending <= 4'd0;
            selected <= 1'b0;
            selected_ch <= 2'd0;
            priority_ch <= 2'd0;
            transfer_idx <= 8'd0;
            for (ch = 0; ch < 4; ch = ch + 1) begin
                log2_n[ch] <= 4'd0;
                ifft[ch] <= 1'b0;
                scale_mode[ch] <= 2'd0;
                shift_mask[ch] <= 8'd0;
                overlap_mode[ch] <= 1'b0;
                window_mode[ch] <= 2'd0;
                fill_count[ch] <= 9'd0;
                write_ptr[ch] <= 8'd0;
                frame_base[ch] <= 8'd0;
            end
        end else begin
            if (input_accept) begin
                if (!epoch_valid[ch_id]) begin
                    epoch_valid[ch_id] <= 1'b1;
                    log2_n[ch_id] <= cfg_log2_n;
                    ifft[ch_id] <= cfg_ifft;
                    scale_mode[ch_id] <= cfg_scale_mode;
                    shift_mask[ch_id] <= cfg_stage_shift_mask;
                    overlap_mode[ch_id] <= cfg_overlap_mode;
                    window_mode[ch_id] <= cfg_window_mode;
                end
                write_ptr[ch_id] <= next_write_ptr;
                fill_count[ch_id] <= fill_count[ch_id] + 9'd1;
                if (fill_count[ch_id] == input_n - 9'd1) begin
                    pending[ch_id] <= 1'b1;
                    frame_base[ch_id] <= next_write_ptr;
                    if (!input_overlap)
                        epoch_valid[ch_id] <= 1'b0;
                end
            end

            if (!selected) begin
                if (found) begin
                    selected <= 1'b1;
                    selected_ch <= chosen_ch;
                    transfer_idx <= 8'd0;
                end
            end else if (f_valid && f_ready) begin
                if (f_last) begin
                    selected <= 1'b0;
                    transfer_idx <= 8'd0;
                    pending[selected_ch] <= 1'b0;
                    priority_ch <= selected_ch + 2'd1;
                    if (overlap_mode[selected_ch])
                        fill_count[selected_ch] <= selected_n >> 1;
                    else
                        fill_count[selected_ch] <= 9'd0;
                end else
                    transfer_idx <= transfer_idx + 8'd1;
            end
        end
    end
endmodule
