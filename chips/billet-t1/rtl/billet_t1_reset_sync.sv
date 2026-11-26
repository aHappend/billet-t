module billet_t1_reset_sync (
    input wire clk, reset,
    output wire rst_n
);
    (* altera_attribute = "-name SYNCHRONIZER_IDENTIFICATION \"FORCED IF ASYNCHRONOUS\"" *)
    reg [1:0] release_sync /* synthesis preserve dont_replicate */ = '0;
    always @(posedge clk or posedge reset)
        if (reset) release_sync <= '0;
        else release_sync <= {release_sync[0], 1'b1};
    assign rst_n = release_sync[1];
endmodule
