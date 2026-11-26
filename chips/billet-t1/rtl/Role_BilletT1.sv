module Role_BilletT1 #(
    parameter integer N_POINTS = 256,
    parameter integer WATCHDOG_CYCLES = 16777216
) (
    input wire clk, reset,
    input wire reg_read, reg_write,
    input wire [17:0] reg_addr,
    input wire [63:0] reg_wdata,
    output wire [63:0] reg_rdata,
    output reg reg_rvalid,
    output wire [31:0] role_id, role_version, role_status,

    input wire ddr_clk, ddr_reset, amm_ready,
    output wire amm_read, amm_write,
    output wire [25:0] amm_address,
    input wire [511:0] amm_readdata,
    output wire [511:0] amm_writedata,
    output wire [6:0] amm_burstcount,
    output wire [63:0] amm_byteenable,
    input wire amm_readdatavalid,

    output wire dma_cmd_valid, dma_cmd_write,
    input wire dma_cmd_ready,
    output wire [63:0] dma_cmd_addr,
    output wire [25:0] dma_cmd_bytes,
    input wire dma_cpl_valid, dma_cpl_error, dma_abort,
    output wire dma_cpl_ready,
    output wire dma_tx_valid, dma_tx_last,
    input wire dma_tx_ready,
    output wire [127:0] dma_tx_data,
    output wire [15:0] dma_tx_keep,
    input wire dma_rx_valid, dma_rx_last,
    output wire dma_rx_ready,
    input wire [127:0] dma_rx_data,
    input wire [15:0] dma_rx_keep
);
    localparam [63:0] MAGIC = 64'h4249_4c4c_4554_5431;
    localparam [31:0] ROLE_ID = 32'h0002_4254, ROLE_VERSION = 32'h0002_0000;
    localparam [31:0] E_MODE=1, E_DDR_ALIGN=2, E_DDR_RANGE=3, E_HOST_ALIGN=4,
        E_HOST_RANGE=5, E_DMA=6, E_BUSY=7, E_STAGE=8, E_ABORT=9,
        E_INCOMPLETE=10, E_UNAVAILABLE=11;
    localparam integer A = N_POINTS > 1 ? $clog2(N_POINTS) : 1;
    localparam integer FRAME_BYTES = N_POINTS * 4;
    localparam integer DDR_BEATS = (FRAME_BYTES + 63) / 64;
    localparam integer STREAM_WORDS = (FRAME_BYTES + 15) / 16;
    localparam integer S = STREAM_WORDS > 1 ? $clog2(STREAM_WORDS) : 1;
    localparam integer W = WATCHDOG_CYCLES > 1 ? $clog2(WATCHDOG_CYCLES) : 1;
    localparam [15:0] LAST_SAMPLE = 16'(N_POINTS - 1);
    localparam [63:0] DDR_LIMIT = 64'h8000_0000 - 64'(DDR_BEATS * 64);
    localparam [63:0] HOST_LIMIT = 64'hffff_ffff_ffff_ffff - (64'(FRAME_BYTES) - 64'd1);

    typedef enum logic [4:0] {
        IDLE, STAGE_ADDR, STAGE_CAPTURE, STAGE_FEED, DMA_IN_CMD, DMA_IN_WAIT, RX_FETCH, RX_PACK,
        DDR_INPUT_WRITE, DDR_READ_CMD, DDR_READ_WAIT, DDR_UNPACK, FFT_OUTPUT,
        DDR_OUTPUT_WRITE, DDR_TX_CMD, DDR_TX_WAIT, TX_STORE, DMA_OUT_CMD,
        DMA_OUT_WAIT, FINISH
    } state_t;
    state_t state;
    typedef struct packed {
        logic tag, final_status, aborted, dma_fault;
        logic [31:0] fft_cycles, ddr_reads, ddr_writes, pcie_reads, pcie_writes;
        logic [31:0] clamps;
        logic overflow;
        logic [31:0] bin0, bin1, bin2, bin3, elapsed_cycles;
        logic [15:0] inputs, outputs;
    } telemetry_t;
    localparam integer STATUS_W = $bits(telemetry_t);

    wire csr_rst_n, fft_rst_n, link_csr_up, link_ddr_up;
    wire link_reset = reset || ddr_reset;
    billet_t1_reset_sync csr_reset (.clk(clk), .reset(reset), .rst_n(csr_rst_n));
    billet_t1_reset_sync fft_reset (.clk(ddr_clk), .reset(ddr_reset), .rst_n(fft_rst_n));
    billet_t1_reset_sync csr_link_reset (.clk(clk), .reset(link_reset), .rst_n(link_csr_up));
    billet_t1_reset_sync ddr_link_reset (.clk(ddr_clk), .reset(link_reset), .rst_n(link_ddr_up));

    reg [63:0] mode_reg, ddr_src_reg, ddr_dst_reg, host_src_reg, host_dst_reg;
    reg busy, done_sticky, error_sticky, output_owned, job_tag;
    reg abort_hold /* synthesis preserve dont_replicate */;
    reg active_dma_job, dma_job_lost /* synthesis preserve dont_replicate */;
    reg [31:0] error_code, completed_jobs;
    reg [N_POINTS-1:0] stage_valid;
    reg [W-1:0] watchdog;
    telemetry_t visible, snapshot_in, snapshot_out;
    reg [63:0] register_read, registered_read;
    reg [1:0] read_kind;

    reg ready_ddr /* synthesis preserve dont_replicate */;
    reg quiet_ddr /* synthesis preserve dont_replicate */;
    (* altera_attribute = "-name SYNCHRONIZER_IDENTIFICATION \"FORCED IF ASYNCHRONOUS\"" *)
    reg [1:0] ready_csr /* synthesis preserve dont_replicate */;
    (* altera_attribute = "-name SYNCHRONIZER_IDENTIFICATION \"FORCED IF ASYNCHRONOUS\"" *)
    reg [1:0] quiet_csr /* synthesis preserve dont_replicate */;
    (* altera_attribute = "-name SYNCHRONIZER_IDENTIFICATION \"FORCED IF ASYNCHRONOUS\"" *)
    reg [1:0] abort_ack_csr /* synthesis preserve dont_replicate */;
    (* altera_attribute = "-name SYNCHRONIZER_IDENTIFICATION \"FORCED IF ASYNCHRONOUS\"" *)
    reg [1:0] abort_ddr /* synthesis preserve dont_replicate */;
    (* altera_attribute = "-name SYNCHRONIZER_IDENTIFICATION \"FORCED IF ASYNCHRONOUS\"" *)
    reg [1:0] dma_lost_ddr /* synthesis preserve dont_replicate */;
    always @(posedge ddr_clk or negedge fft_rst_n) begin
        if (!fft_rst_n) begin
            ready_ddr <= 0;
            abort_ddr <= '0;
            dma_lost_ddr <= '0;
        end else begin
            ready_ddr <= amm_ready;
            abort_ddr <= {abort_ddr[0], abort_hold};
            dma_lost_ddr <= {dma_lost_ddr[0], dma_job_lost};
        end
    end
    always @(posedge ddr_clk or negedge link_ddr_up)
        if (!link_ddr_up) quiet_ddr <= 0;
        else quiet_ddr <= (state == IDLE && !(command_valid && command_take)) ||
                          (state == FINISH && snapshot_ready);
    always @(posedge clk or negedge link_csr_up) begin
        if (!link_csr_up) begin
            ready_csr <= '0;
            quiet_csr <= '0;
            abort_ack_csr <= '0;
        end else begin
            ready_csr <= {ready_csr[0], ready_ddr};
            quiet_csr <= {quiet_csr[0], quiet_ddr};
            abort_ack_csr <= {abort_ack_csr[0], abort_ddr[1]};
        end
    end

    wire input_window = reg_addr >= 18'h01000 && reg_addr < 18'h01000 + 18'(N_POINTS);
    wire output_window = reg_addr >= 18'h02000 && reg_addr < 18'h02000 + 18'(N_POINTS);
    wire [A-1:0] csr_addr = reg_addr[A-1:0];
    wire quarantine = abort_hold || abort_ack_csr[1];
    wire stage_access = !busy && !quarantine;
    wire control_write = reg_write && reg_addr == 18'd3;
    wire abort_write = control_write && reg_wdata[1];
    wire clear_write = control_write && reg_wdata[2] && !abort_write;
    wire start_write = control_write && reg_wdata[0] && !abort_write && !clear_write;
    wire overdue = busy && watchdog == W'(WATCHDOG_CYCLES - 1);
    wire dma_available;
    reg [31:0] validation_error;
    always @* begin
        validation_error = 0;
        if (mode_reg > 2) validation_error = E_MODE;
        else if (mode_reg != 0 && (ddr_src_reg[5:0] != 0 || ddr_dst_reg[5:0] != 0))
            validation_error = E_DDR_ALIGN;
        else if (mode_reg != 0 && (ddr_src_reg > DDR_LIMIT || ddr_dst_reg > DDR_LIMIT))
            validation_error = E_DDR_RANGE;
        else if (mode_reg == 2 && (host_src_reg[4:0] != 0 || host_dst_reg[4:0] != 0))
            validation_error = E_HOST_ALIGN;
        else if (mode_reg == 2 && (host_src_reg > HOST_LIMIT || host_dst_reg > HOST_LIMIT))
            validation_error = E_HOST_RANGE;
        else if (mode_reg == 0 && !(&stage_valid)) validation_error = E_INCOMPLETE;
        else if (mode_reg == 2 && !dma_available) validation_error = E_UNAVAILABLE;
    end

    wire command_ready, command_valid, snapshot_ready, snapshot_valid;
    wire [180:0] command_payload;
    wire start_ready = command_ready && quiet_csr[1];
    wire accept_start = start_write && stage_access && start_ready && validation_error == 0;
    wire command_take = state == IDLE && snapshot_ready && link_ddr_up;
    billet_t1_mailbox #(.WIDTH(181)) descriptor_mailbox (
        .src_clk(clk), .src_rst_n(link_csr_up), .src_send(accept_start),
        .src_data({!job_tag, mode_reg[1:0], ddr_src_reg[30:6], ddr_dst_reg[30:6],
                   host_src_reg, host_dst_reg}), .src_ready(command_ready),
        .dst_clk(ddr_clk), .dst_rst_n(link_ddr_up), .dst_valid(command_valid),
        .dst_data(command_payload), .dst_accept(command_take)
    );
    billet_t1_mailbox #(.WIDTH(STATUS_W)) status_mailbox (
        .src_clk(ddr_clk), .src_rst_n(link_ddr_up),
        .src_send(state != IDLE), .src_data(snapshot_out), .src_ready(snapshot_ready),
        .dst_clk(clk), .dst_rst_n(link_csr_up), .dst_valid(snapshot_valid),
        .dst_data(snapshot_in), .dst_accept(1'b1)
    );

    wire stage_write = csr_rst_n && reg_write && input_window && stage_access;
    wire input_read = reg_read && input_window && stage_access && stage_valid[csr_addr];
    wire output_read = reg_read && output_window && stage_access && output_owned;
    wire [31:0] stage_sample, csr_input_sample, csr_output_sample;
    reg [A:0] stage_reads;
    wire stage_fetch;
    billet_t1_frame_ram #(.DEPTH(N_POINTS), .ADDR_W(A)) input_frame (
        .wr_clk(clk), .wr_en(stage_write), .wr_addr(csr_addr), .wr_data(reg_wdata[31:0]),
        .rd_clk(ddr_clk), .rd_en(stage_fetch), .rd_addr(stage_reads[A-1:0]),
        .rd_data(stage_sample)
    );
    billet_t1_frame_ram #(.DEPTH(N_POINTS), .ADDR_W(A), .RAM_STYLE("M20K")) input_readback (
        .wr_clk(clk), .wr_en(stage_write), .wr_addr(csr_addr), .wr_data(reg_wdata[31:0]),
        .rd_clk(clk), .rd_en(input_read), .rd_addr(csr_addr), .rd_data(csr_input_sample)
    );
    assign role_id = ROLE_ID;
    assign role_version = ROLE_VERSION;
    assign role_status = {28'b0, ready_csr[1], error_sticky, done_sticky, busy};
    assign reg_rdata = !reg_rvalid ? 64'b0 : read_kind == 1 ? {32'b0, csr_input_sample} :
                       read_kind == 2 ? {32'b0, csr_output_sample} : registered_read;
    always @* begin
        case (reg_addr)
            0: register_read = MAGIC;
            1: register_read = {ROLE_VERSION, ROLE_ID};
            2: register_read = {61'b0, error_sticky, done_sticky, busy};
            4: register_read = mode_reg;
            5: register_read = ddr_src_reg;
            6: register_read = ddr_dst_reg;
            7: register_read = host_src_reg;
            8: register_read = host_dst_reg;
            9: register_read = 64'(N_POINTS);
            10: register_read = {32'b0, error_code};
            11: register_read = {32'b0, visible.fft_cycles};
            12: register_read = {visible.ddr_writes, visible.ddr_reads};
            13: register_read = {visible.pcie_writes, visible.pcie_reads};
            14: register_read = {32'b0, completed_jobs};
            15: register_read = {31'b0, visible.clamps, visible.overflow};
            16: register_read = {32'b0, visible.bin0};
            17: register_read = {32'b0, visible.bin1};
            18: register_read = {32'b0, visible.bin2};
            19: register_read = {32'b0, visible.bin3};
            20: register_read = {32'b0, visible.elapsed_cycles};
            21: register_read = {32'b0, visible.outputs, visible.inputs};
            default: register_read = 0;
        endcase
    end

    always @(posedge clk or negedge csr_rst_n) begin
        if (!csr_rst_n) begin
            {mode_reg, ddr_src_reg, ddr_dst_reg, host_src_reg, host_dst_reg} <= '0;
            {busy, done_sticky, error_sticky, output_owned, job_tag, abort_hold} <= '0;
            {active_dma_job, dma_job_lost} <= '0;
            error_code <= 0;
            completed_jobs <= 0;
            stage_valid <= '0;
            watchdog <= '0;
            visible <= '0;
            reg_rvalid <= 0;
            registered_read <= 0;
            read_kind <= 0;
        end else begin
            reg_rvalid <= reg_read;
            registered_read <= register_read;
            read_kind <= input_read ? 2'd1 : output_read ? 2'd2 : 2'd0;
            watchdog <= busy ? watchdog + 1'b1 : '0;
            if (stage_write) stage_valid[csr_addr] <= 1;
            if (busy && active_dma_job && dma_abort) dma_job_lost <= 1;
            if (abort_hold && !busy && command_ready && quiet_csr[1] && abort_ack_csr[1])
                abort_hold <= 0;

            if (reg_write) begin
                case (reg_addr)
                    4: mode_reg <= reg_wdata;
                    5: ddr_src_reg <= reg_wdata;
                    6: ddr_dst_reg <= reg_wdata;
                    7: host_src_reg <= reg_wdata;
                    8: host_dst_reg <= reg_wdata;
                    default: ;
                endcase
            end
            if (clear_write) begin
                done_sticky <= 0;
                error_sticky <= 0;
                error_code <= 0;
            end
            if (snapshot_valid && snapshot_in.tag == job_tag && busy && link_csr_up) begin
                visible <= snapshot_in;
                if (snapshot_in.final_status) begin
                    busy <= 0;
                    if (abort_hold || snapshot_in.aborted || dma_job_lost ||
                        (active_dma_job && dma_abort) || snapshot_in.dma_fault) begin
                        error_sticky <= 1;
                        error_code <= !abort_hold && snapshot_in.dma_fault ? E_DMA : E_ABORT;
                        output_owned <= 0;
                    end else if (!overdue && !abort_write) begin
                        done_sticky <= !clear_write;
                        output_owned <= 1;
                        completed_jobs <= completed_jobs + 1'b1;
                    end
                end
            end
            if (((reg_read || reg_write) && (input_window || output_window) && !stage_access) ||
                (reg_write && output_window)) begin
                error_sticky <= 1;
                error_code <= E_STAGE;
            end
            if (start_write) begin
                if (accept_start) begin
                    busy <= 1;
                    done_sticky <= 0;
                    output_owned <= 0;
                    job_tag <= !job_tag;
                    active_dma_job <= mode_reg == 2;
                    dma_job_lost <= 0;
                    visible <= '0;
                    visible.clamps <= visible.clamps;
                    visible.overflow <= visible.overflow;
                end else begin
                    error_sticky <= 1;
                    if (!stage_access) error_code <= E_BUSY;
                    else begin
                        done_sticky <= 0;
                        error_code <= validation_error != 0 ? validation_error : E_UNAVAILABLE;
                    end
                end
            end
            if (abort_hold || !link_csr_up || abort_write || overdue) begin
                visible.clamps <= 0;
                visible.overflow <= 0;
            end
            if (!link_csr_up) begin
                output_owned <= 0;
                done_sticky <= 0;
            end
            if ((busy && !link_csr_up) || overdue || abort_write) begin
                if (!link_csr_up || overdue) busy <= 0;
                abort_hold <= 1;
                stage_valid <= '0;
                output_owned <= 0;
                done_sticky <= 0;
                error_sticky <= 1;
                error_code <= overdue && !abort_write && link_csr_up ? E_UNAVAILABLE : E_ABORT;
            end
        end
    end

    reg active_tag, cancelled, dma_fault, fft_counting;
    reg [1:0] active_mode;
    reg [24:0] ddr_src, ddr_dst;
    reg [63:0] host_src, host_dst;
    reg [3:0] beat_index, lane;
    reg [S-1:0] stream_index;
    reg [1:0] quarter;
    reg [511:0] beat_data;
    reg [31:0] fft_cycles, elapsed_cycles, ddr_reads, ddr_writes, pcie_reads, pcie_writes;
    reg [31:0] bin0, bin1, bin2, bin3;
    reg [15:0] input_count, output_count;
    reg core_job_reset;
    always @(posedge ddr_clk or negedge fft_rst_n)
        if (!fft_rst_n) core_job_reset <= 0;
        else core_job_reset <= state == FINISH &&
                              (cancelled || dma_fault || (active_mode == 2 && dma_lost_ddr[1]));
    wire core_rst_n = fft_rst_n && link_ddr_up && !abort_ddr[1] && !core_job_reset;
    wire cancel_now = cancelled || !core_rst_n || (active_mode == 2 && dma_lost_ddr[1]);
    wire core_in_ready, core_out_valid, core_out_last, core_overflow;
    wire [31:0] core_clamps;
    wire signed [15:0] core_out_re, core_out_im;
    wire [A-1:0] core_bin;
    wire core_in_valid = !cancel_now && (state == STAGE_FEED || state == DDR_UNPACK);
    wire core_out_ready = !cancel_now && state == FFT_OUTPUT;
    wire input_take = core_in_valid && core_in_ready;
    wire output_take = core_out_valid && core_out_ready;
    reg [31:0] stage_input /* synthesis preserve */;
    wire stage_advance = state == STAGE_FEED && input_take;
    // Prime the RAM and timing register, then advance both only on acceptance.
    // The high bit stops reads after N_POINTS without wrapping the RAM address.
    assign stage_fetch = !cancel_now && !stage_reads[A] &&
                         (state == STAGE_ADDR || state == STAGE_CAPTURE || stage_advance);
    always @(posedge ddr_clk) begin
        if (state == IDLE)
            stage_reads <= '0;
        else if (stage_fetch)
            stage_reads <= stage_reads + 1'b1;
        if (state == STAGE_CAPTURE || stage_advance)
            stage_input <= stage_sample;
    end
    wire [31:0] core_input = state == STAGE_FEED ? stage_input : beat_data[31:0];
    wire [31:0] packed_result = {core_out_im, core_out_re};
    billet_t1_top #(.N_POINTS(N_POINTS)) fft (
        .clk(ddr_clk), .rst_n(core_rst_n),
        .in_valid(core_in_valid), .in_last(input_count == LAST_SAMPLE),
        .in_re(core_input[15:0]), .in_im(core_input[31:16]), .in_ready(core_in_ready),
        .out_ready(core_out_ready), .out_valid(core_out_valid), .out_last(core_out_last),
        .out_re(core_out_re), .out_im(core_out_im), .out_bin_idx(core_bin),
        .frame_done(), .overflow_flag(core_overflow), .saturation_count(core_clamps)
    );
    billet_t1_frame_ram #(.DEPTH(N_POINTS), .ADDR_W(A)) output_frame (
        .wr_clk(ddr_clk), .wr_en(output_take), .wr_addr(core_bin), .wr_data(packed_result),
        .rd_clk(clk), .rd_en(output_read), .rd_addr(csr_addr), .rd_data(csr_output_sample)
    );
    assign snapshot_out = {
        active_tag, state == FINISH, cancel_now, dma_fault, fft_cycles,
        ddr_reads, ddr_writes, pcie_reads, pcie_writes, core_clamps, core_overflow,
        bin0, bin1, bin2, bin3, elapsed_cycles, input_count, output_count
    };

    wire dma_request_ready, dma_request_valid, dma_request_take;
    wire [64:0] dma_request;
    wire dma_result_ready, dma_result_valid, dma_result_send;
    wire [33:0] dma_result;
    wire dma_error, dma_cancelled;
    wire [31:0] dma_beats;
    wire dma_out = state == DMA_OUT_CMD;
    billet_t1_mailbox #(.WIDTH(65)) dma_request_mailbox (
        .src_clk(ddr_clk), .src_rst_n(link_ddr_up),
        .src_send(!cancel_now && (state == DMA_IN_CMD || dma_out)),
        .src_data({dma_out, dma_out ? host_dst : host_src}), .src_ready(dma_request_ready),
        .dst_clk(clk), .dst_rst_n(link_csr_up), .dst_valid(dma_request_valid),
        .dst_data(dma_request), .dst_accept(dma_request_take)
    );
    billet_t1_mailbox #(.WIDTH(34)) dma_result_mailbox (
        .src_clk(clk), .src_rst_n(link_csr_up), .src_send(dma_result_send),
        .src_data({dma_error, dma_cancelled, dma_beats}), .src_ready(dma_result_ready),
        .dst_clk(ddr_clk), .dst_rst_n(link_ddr_up), .dst_valid(dma_result_valid),
        .dst_data(dma_result), .dst_accept(1'b1)
    );
    wire frame_rx_we, frame_tx_re;
    wire [S-1:0] dma_stream_index;
    wire [127:0] dma_frame_rx, dma_frame_tx, rx_word;
    billet_t1_role_dma #(.FRAME_BYTES(FRAME_BYTES), .INDEX_W(S)) dma (
        .clk(clk), .rst_n(csr_rst_n), .link_up(link_csr_up), .cancel(abort_hold || dma_job_lost),
        .request_valid(dma_request_valid), .request_write(dma_request[64]),
        .request_addr(dma_request[63:0]), .request_take(dma_request_take),
        .available(dma_available), .result_ready(dma_result_ready), .result_send(dma_result_send),
        .result_error(dma_error), .result_cancelled(dma_cancelled), .native_beats(dma_beats),
        .frame_rx_we(frame_rx_we), .frame_tx_re(frame_tx_re), .frame_index(dma_stream_index),
        .frame_rx_data(dma_frame_rx), .frame_tx_data(dma_frame_tx), .*
    );
    billet_t1_frame_ram #(.WIDTH(128), .DEPTH(STREAM_WORDS), .ADDR_W(S)) rx_frame (
        .wr_clk(clk), .wr_en(frame_rx_we), .wr_addr(dma_stream_index), .wr_data(dma_frame_rx),
        .rd_clk(ddr_clk), .rd_en(state == RX_FETCH), .rd_addr(stream_index), .rd_data(rx_word)
    );
    billet_t1_frame_ram #(.WIDTH(128), .DEPTH(STREAM_WORDS), .ADDR_W(S)) tx_frame (
        .wr_clk(ddr_clk), .wr_en(state == TX_STORE && !cancel_now), .wr_addr(stream_index),
        .wr_data(beat_data[127:0]), .rd_clk(clk), .rd_en(frame_tx_re),
        .rd_addr(dma_stream_index), .rd_data(dma_frame_tx)
    );

    wire input_ddr = state == DDR_READ_CMD || state == DDR_READ_WAIT || state == DDR_INPUT_WRITE;
    wire [24:0] ddr_word = (input_ddr ? ddr_src : ddr_dst) + 25'(beat_index);
    assign amm_read = fft_rst_n && (state == DDR_READ_CMD || state == DDR_TX_CMD);
    assign amm_write = fft_rst_n && (state == DDR_INPUT_WRITE || state == DDR_OUTPUT_WRITE);
    assign amm_address = {1'b0, ddr_word};
    assign amm_writedata = beat_data;
    assign amm_byteenable = '1;
    assign amm_burstcount = 7'd1;
    wire ddr_accept_read = amm_read && amm_ready;
    wire ddr_accept_write = amm_write && amm_ready;
    wire ddr_capture = amm_readdatavalid && (ddr_accept_read ||
                       state == DDR_READ_WAIT || state == DDR_TX_WAIT);
    wire last_ddr_beat = beat_index == 4'(DDR_BEATS - 1);
    wire last_stream_word = stream_index == S'(STREAM_WORDS - 1);

    always @(posedge ddr_clk or negedge fft_rst_n) begin
        if (!fft_rst_n) begin
            state <= IDLE;
            {active_tag, active_mode, ddr_src, ddr_dst, host_src, host_dst} <= '0;
            {cancelled, dma_fault, fft_counting} <= '0;
            {beat_index, lane, stream_index, quarter} <= '0;
            {fft_cycles, elapsed_cycles, ddr_reads, ddr_writes, pcie_reads, pcie_writes} <= '0;
            {bin0, bin1, bin2, bin3, input_count, output_count} <= '0;
        end else begin
            if (state != IDLE && state != FINISH) elapsed_cycles <= elapsed_cycles + 1'b1;
            if (state != IDLE && cancel_now) cancelled <= 1;
            if (ddr_accept_read) ddr_reads <= ddr_reads + 1'b1;
            if (ddr_accept_write) ddr_writes <= ddr_writes + 1'b1;
            if (fft_counting) fft_cycles <= fft_cycles + 1'b1;
            if (input_take) begin
                input_count <= input_count + 1'b1;
                if (input_count == 0) begin fft_counting <= 1; fft_cycles <= 1; end
            end
            if (output_take) begin
                output_count <= output_count + 1'b1;
                if (core_out_last) fft_counting <= 0;
                case (int'(core_bin))
                    0: bin0 <= packed_result;
                    1: bin1 <= packed_result;
                    2: bin2 <= packed_result;
                    3: bin3 <= packed_result;
                    default: ;
                endcase
            end
            case (state)
                IDLE: if (command_valid && command_take) begin
                    {active_tag, active_mode, ddr_src, ddr_dst, host_src, host_dst} <= command_payload;
                    {cancelled, dma_fault, fft_counting} <= '0;
                    {beat_index, lane, stream_index, quarter} <= '0;
                    {fft_cycles, elapsed_cycles, ddr_reads, ddr_writes, pcie_reads, pcie_writes} <= '0;
                    {bin0, bin1, bin2, bin3, input_count, output_count} <= '0;
                    if (!core_rst_n) state <= FINISH;
                    else case (command_payload[179:178])
                        0: state <= STAGE_ADDR;
                        1: state <= DDR_READ_CMD;
                        default: state <= DMA_IN_CMD;
                    endcase
                end
                STAGE_ADDR: state <= cancel_now ? FINISH : STAGE_CAPTURE;
                STAGE_CAPTURE: state <= cancel_now ? FINISH : STAGE_FEED;
                STAGE_FEED: if (cancel_now) state <= FINISH;
                else if (input_take && input_count == LAST_SAMPLE) state <= FFT_OUTPUT;
                DMA_IN_CMD, DMA_OUT_CMD: if (cancel_now) state <= FINISH;
                else if (dma_request_ready) state <= dma_out ? DMA_OUT_WAIT : DMA_IN_WAIT;
                DMA_IN_WAIT, DMA_OUT_WAIT: if (!link_ddr_up) state <= FINISH;
                else if (dma_result_valid) begin
                    {dma_fault, cancelled} <= {dma_result[33], cancel_now || dma_result[32]};
                    if (state == DMA_IN_WAIT) pcie_reads <= dma_result[31:0];
                    else pcie_writes <= dma_result[31:0];
                    state <= state == DMA_IN_WAIT && !cancel_now && dma_result[33:32] == 0 ?
                             RX_FETCH : FINISH;
                end
                RX_FETCH: state <= cancel_now ? FINISH : RX_PACK;
                RX_PACK: if (cancel_now) state <= FINISH;
                else begin
                    stream_index <= stream_index + 1'b1;
                    quarter <= quarter + 1'b1;
                    state <= quarter == 3 || last_stream_word ? DDR_INPUT_WRITE : RX_FETCH;
                end
                DDR_INPUT_WRITE: if (ddr_accept_write) begin
                    if (cancel_now) state <= FINISH;
                    else if (last_ddr_beat) begin beat_index <= 0; state <= DDR_READ_CMD; end
                    else begin beat_index <= beat_index + 1'b1; state <= RX_FETCH; end
                end
                DDR_READ_CMD, DDR_TX_CMD: if (ddr_accept_read && !amm_readdatavalid)
                    state <= state == DDR_READ_CMD ? DDR_READ_WAIT : DDR_TX_WAIT;
                else if (ddr_capture) begin
                    lane <= 0;
                    state <= cancel_now ? FINISH : state == DDR_READ_CMD ? DDR_UNPACK : TX_STORE;
                end
                DDR_READ_WAIT, DDR_TX_WAIT: if (ddr_capture) begin
                    lane <= 0;
                    state <= cancel_now ? FINISH : state == DDR_READ_WAIT ? DDR_UNPACK : TX_STORE;
                end
                DDR_UNPACK: if (cancel_now) state <= FINISH;
                else if (input_take) begin
                    lane <= lane + 1'b1;
                    if (input_count == LAST_SAMPLE) begin
                        beat_index <= 0;
                        lane <= 0;
                        state <= FFT_OUTPUT;
                    end else if (lane == 15) begin
                        beat_index <= beat_index + 1'b1;
                        state <= DDR_READ_CMD;
                    end
                end
                FFT_OUTPUT: if (cancel_now) state <= FINISH;
                else if (output_take) begin
                    if (active_mode == 0) begin
                        if (core_out_last) state <= FINISH;
                    end else begin
                        lane <= lane + 1'b1;
                        if (core_out_last || lane == 15) state <= DDR_OUTPUT_WRITE;
                    end
                end
                DDR_OUTPUT_WRITE: if (ddr_accept_write) begin
                    lane <= 0;
                    if (cancel_now) state <= FINISH;
                    else if (output_count == 16'(N_POINTS)) begin
                        {beat_index, stream_index, quarter} <= '0;
                        state <= active_mode == 1 ? FINISH : DDR_TX_CMD;
                    end else begin beat_index <= beat_index + 1'b1; state <= FFT_OUTPUT; end
                end
                TX_STORE: if (cancel_now) state <= FINISH;
                else begin
                    stream_index <= stream_index + 1'b1;
                    quarter <= quarter + 1'b1;
                    if (last_stream_word) state <= DMA_OUT_CMD;
                    else if (quarter == 3) begin
                        beat_index <= beat_index + 1'b1;
                        state <= DDR_TX_CMD;
                    end
                end
                FINISH: begin
                    fft_counting <= 0;
                    if (snapshot_ready || !link_ddr_up) state <= IDLE;
                end
                default: state <= IDLE;
            endcase
        end
    end

    genvar g;
    generate for (g = 0; g < 16; g = g + 1) begin : g_lane
        wire [31:0] shift_sample = (g < 15) ? 32'(beat_data >> ((g+1)*32)) : 32'd0;
        wire [31:0] shift_stream = (g < 12) ? 32'(beat_data >> ((g+4)*32)) : 32'd0;
        always @(posedge ddr_clk) begin
            if (state == IDLE || ddr_accept_write || (state == DDR_UNPACK && input_take &&
                input_count == LAST_SAMPLE))
                beat_data[g*32 +: 32] <= 0;
            else if (ddr_capture) beat_data[g*32 +: 32] <= amm_readdata[g*32 +: 32];
            else if (state == RX_PACK && quarter == 2'(g / 4))
                beat_data[g*32 +: 32] <= rx_word[(g%4)*32 +: 32];
            else if (state == DDR_UNPACK && input_take) beat_data[g*32 +: 32] <= shift_sample;
            else if (state == TX_STORE) beat_data[g*32 +: 32] <= shift_stream;
            else if (state == FFT_OUTPUT && output_take && active_mode != 0 && lane == 4'(g))
                beat_data[g*32 +: 32] <= packed_result;
        end
    end endgenerate

    initial begin
        if (N_POINTS < 2 || N_POINTS > 256 || (N_POINTS & (N_POINTS - 1)) != 0)
            $fatal(1, "PARAMETER ERROR: Role_BilletT1 requires power-of-two N_POINTS in [2,256]");
        if (WATCHDOG_CYCLES < 1)
            $fatal(1, "PARAMETER ERROR: WATCHDOG_CYCLES must be positive");
    end
endmodule
