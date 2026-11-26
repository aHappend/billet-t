module billet_t1_role_dma #(
    parameter integer FRAME_BYTES = 1024,
    parameter integer INDEX_W = FRAME_BYTES > 16 ? $clog2((FRAME_BYTES + 15) / 16) : 1
) (
    input wire clk, rst_n, link_up, cancel,
    input wire request_valid, request_write,
    input wire [63:0] request_addr,
    output wire request_take, available,
    input wire result_ready,
    output wire result_send, result_error, result_cancelled,
    output reg [31:0] native_beats,

    output wire frame_rx_we, frame_tx_re,
    output reg [INDEX_W-1:0] frame_index,
    output wire [127:0] frame_rx_data,
    input wire [127:0] frame_tx_data,

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
    typedef enum logic [3:0] {
        IDLE, PLAN, COMMAND, RX, TX_FETCH, TX_SEND, WAIT_RESULT, NATIVE_LOST, RESPOND
    } state_t;
    state_t state;
    typedef enum logic [2:0] {
        OPEN, FAULT_ASSERT, FAULT_RELEASE, LOCAL_RELEASE, NATIVE_ASSERT
    } guard_t;
    guard_t guard = OPEN;
    reg command_owned = 0;
    reg write_job, cancelled, discard_result, failed, cpl_seen;
    reg [63:0] address;
    reg [10:0] frame_left;
    reg [7:0] length, chunk_left;

    wire cancel_now = cancel || !link_up || cancelled;
    wire transfer = state == RX || state == TX_FETCH || state == TX_SEND ||
                    state == WAIT_RESULT;
    wire cpl_failure = (transfer || state == NATIVE_LOST) && dma_cpl_valid && dma_cpl_error;
    wire retired = state == WAIT_RESULT && (cpl_seen || dma_cpl_valid) &&
                   !cpl_failure && !dma_abort;
    wire [8:0] rounded_length = {1'b0, length} + 9'd31;
    wire [12:0] page_left = 13'd4096 - {1'b0, address[11:0]};
    wire [7:0] chunk_limit = frame_left > 11'd128 ? 8'd128 : frame_left[7:0];
    wire [7:0] next_length = page_left < {5'b0, chunk_limit} ? page_left[7:0] : chunk_limit;
    wire [4:0] stream_bytes = chunk_left >= 8'd16 ? 5'd16 : chunk_left[4:0];
    wire [15:0] keep = 16'hffff >> (5'd16 - stream_bytes);
    wire stream_last = chunk_left <= 8'd16;
    wire tx_take = dma_tx_valid && dma_tx_ready;
    wire rx_take = dma_rx_valid && dma_rx_ready;
    wire rx_bad = rx_take && (dma_rx_keep != keep || dma_rx_last != stream_last ||
                              chunk_left == 0);

    assign available = rst_n && state == IDLE && guard == OPEN && !dma_abort;
    assign request_take = rst_n && link_up && state == IDLE;
    assign result_send = state == RESPOND && link_up && !discard_result && result_ready;
    assign result_error = failed;
    assign result_cancelled = cancel_now;
    assign dma_cmd_valid = rst_n && state == COMMAND && !cancel_now &&
                           guard == OPEN && !dma_abort;
    assign dma_cmd_write = write_job;
    assign dma_cmd_addr = address;
    assign dma_cmd_bytes = {18'b0, length};
    assign dma_cpl_ready = 1'b1;
    assign dma_tx_valid = rst_n && state == TX_SEND && !dma_abort;
    assign dma_tx_keep = keep;
    assign dma_tx_last = stream_last;
    assign dma_rx_ready = rst_n && state == RX;
    assign frame_rx_we = rx_take && !cancel_now && !failed && !rx_bad;
    assign frame_tx_re = rst_n && state == TX_FETCH;
    genvar b;
    generate for (b = 0; b < 16; b = b + 1) begin : g_byte
        assign frame_rx_data[b*8 +: 8] = keep[b] ? dma_rx_data[b*8 +: 8] : 8'b0;
        assign dma_tx_data[b*8 +: 8] = keep[b] ? frame_tx_data[b*8 +: 8] : 8'b0;
    end endgenerate

    // A role reset clears the platform queues, not necessarily the native owner.
    // Remember lost ownership across that reset; require a later native reset.
    always @(posedge clk) begin
        if (!rst_n) begin
            if (command_owned || guard == FAULT_ASSERT || guard == FAULT_RELEASE)
                guard <= LOCAL_RELEASE;
            command_owned <= 0;
        end else begin
            if (dma_cmd_valid && dma_cmd_ready) command_owned <= 1;
            if (retired || cpl_failure || (state == NATIVE_LOST && !dma_abort))
                command_owned <= 0;
            case (guard)
                OPEN: if (command_owned && (dma_abort || cpl_failure))
                    guard <= dma_abort ? FAULT_RELEASE : FAULT_ASSERT;
                FAULT_ASSERT, NATIVE_ASSERT: if (dma_abort) guard <= FAULT_RELEASE;
                FAULT_RELEASE: if (!dma_abort) guard <= OPEN;
                LOCAL_RELEASE: if (!dma_abort) guard <= NATIVE_ASSERT;
                default: guard <= LOCAL_RELEASE;
            endcase
        end
    end

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            state <= IDLE;
            write_job <= 0;
            cancelled <= 0;
            discard_result <= 0;
            failed <= 0;
            cpl_seen <= 0;
            native_beats <= 0;
            address <= 0;
            frame_left <= 0;
            frame_index <= 0;
            length <= 0;
            chunk_left <= 0;
        end else begin
            if (state != IDLE) begin
                if (cancel_now) cancelled <= 1;
                if (!link_up) discard_result <= 1;
            end
            if (transfer && dma_cpl_valid) cpl_seen <= 1;

            if (cpl_failure) begin
                failed <= 1;
                state <= RESPOND;
            end else if (transfer && dma_abort) begin
                // A fault can precede its error completion. A reset instead
                // discards the completion and releases abort in a new epoch.
                cancelled <= 1;
                state <= NATIVE_LOST;
            end else case (state)
                IDLE: if (request_valid && request_take) begin
                    write_job <= request_write;
                    address <= request_addr;
                    frame_left <= 11'(FRAME_BYTES);
                    frame_index <= 0;
                    native_beats <= 0;
                    cancelled <= cancel;
                    discard_result <= 0;
                    failed <= !available && !cancel;
                    state <= available && !cancel ? PLAN : RESPOND;
                end
                PLAN, COMMAND: begin
                    if (cancel_now || dma_abort) begin
                        failed <= !cancel_now;
                        state <= RESPOND;
                    end else if (state == PLAN) begin
                        length <= next_length;
                        chunk_left <= next_length;
                        cpl_seen <= 0;
                        state <= COMMAND;
                    end else if (dma_cmd_valid && dma_cmd_ready) begin
                        state <= write_job ? TX_FETCH : RX;
                    end
                end
                RX: if (rx_take) begin
                    if (rx_bad) failed <= 1;
                    if (chunk_left != 0) begin
                        frame_index <= frame_index + 1'b1;
                        chunk_left <= chunk_left - {3'b0, stream_bytes};
                    end
                    if (dma_rx_last) state <= WAIT_RESULT;
                end
                TX_FETCH: state <= TX_SEND;
                TX_SEND: if (tx_take) begin
                    frame_index <= frame_index + 1'b1;
                    chunk_left <= chunk_left - {3'b0, stream_bytes};
                    state <= stream_last ? WAIT_RESULT : TX_FETCH;
                end
                WAIT_RESULT: if (retired) begin
                    native_beats <= native_beats + {28'b0, rounded_length[8:5]};
                    if (cancel_now || failed || frame_left == {3'b0, length}) state <= RESPOND;
                    else begin
                        address <= address + {56'b0, length};
                        frame_left <= frame_left - {3'b0, length};
                        state <= PLAN;
                    end
                end
                NATIVE_LOST: if (!dma_abort) state <= RESPOND;
                RESPOND: if (result_send || discard_result || !link_up) state <= IDLE;
                default: state <= IDLE;
            endcase
        end
    end
endmodule
