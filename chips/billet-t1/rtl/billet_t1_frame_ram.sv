module billet_t1_frame_ram #(
    parameter integer WIDTH = 32,
    parameter integer DEPTH = 256,
    parameter integer ADDR_W = (DEPTH > 1) ? $clog2(DEPTH) : 1,
    parameter RAM_STYLE = "M20K, no_rw_check"
) (
    input wire wr_clk, wr_en,
    input wire [ADDR_W-1:0] wr_addr,
    input wire [WIDTH-1:0] wr_data,
    input wire rd_clk, rd_en,
    input wire [ADDR_W-1:0] rd_addr,
    output reg [WIDTH-1:0] rd_data
);
    (* ramstyle = RAM_STYLE, nomem2reg *) reg [WIDTH-1:0] mem [0:DEPTH-1];
    always @(posedge wr_clk)
        if (wr_en) mem[wr_addr] <= wr_data;
    always @(posedge rd_clk)
        if (rd_en) rd_data <= mem[rd_addr];
endmodule
