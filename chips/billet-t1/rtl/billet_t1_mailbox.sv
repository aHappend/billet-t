module billet_t1_mailbox #(parameter integer WIDTH = 1) (
    input wire src_clk, src_rst_n, src_send,
    input wire [WIDTH-1:0] src_data,
    output wire src_ready,
    input wire dst_clk, dst_rst_n, dst_accept,
    output reg dst_valid,
    output reg [WIDTH-1:0] dst_data /* synthesis preserve dont_replicate */
);
    // Both endpoints share the same reset epoch, with local release in each clock.
    reg [WIDTH-1:0] src_hold /* synthesis preserve dont_replicate */;
    reg request_toggle /* synthesis preserve dont_replicate */;
    reg ack_toggle /* synthesis preserve dont_replicate */;
    (* altera_attribute = "-name SYNCHRONIZER_IDENTIFICATION \"FORCED IF ASYNCHRONOUS\"" *)
    reg [1:0] ack_sync /* synthesis preserve dont_replicate */;
    (* altera_attribute = "-name SYNCHRONIZER_IDENTIFICATION \"FORCED IF ASYNCHRONOUS\"" *)
    reg [1:0] req_sync /* synthesis preserve dont_replicate */;

    assign src_ready = src_rst_n && ack_sync[1] == request_toggle;
    always @(posedge src_clk or negedge src_rst_n) begin
        if (!src_rst_n) begin
            request_toggle <= 0;
            ack_sync <= '0;
        end else begin
            ack_sync <= {ack_sync[0], ack_toggle};
            if (src_send && src_ready) request_toggle <= !request_toggle;
        end
    end
    always @(posedge src_clk)
        if (src_send && src_ready) src_hold <= src_data;

    always @(posedge dst_clk or negedge dst_rst_n) begin
        if (!dst_rst_n) begin
            req_sync <= '0;
            ack_toggle <= 0;
            dst_valid <= 0;
        end else begin
            req_sync <= {req_sync[0], request_toggle};
            if (!dst_valid && req_sync[1] != ack_toggle) dst_valid <= 1;
            else if (dst_valid && dst_accept) begin
                ack_toggle <= req_sync[1];
                dst_valid <= 0;
            end
        end
    end
    always @(posedge dst_clk)
        if (dst_rst_n && !dst_valid && req_sync[1] != ack_toggle)
            dst_data <= src_hold;
endmodule
