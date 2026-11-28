`timescale 1ns/1ps

module billet_shell_case #(parameter int N = 256) (output bit finished);
    import ShellTypes::*;
    localparam int B = (N+15)/16, BYTES = N*4;
    localparam logic [63:0] MAGIC = 64'h42494c4c45545431, IDENT = 64'h0002000000024254;
    localparam logic [63:0] DDR_SRC = 64'h440, DDR_DST = 64'h80000000 - B*64;
    localparam logic [63:0] HOST_SRC = 64'h100001fe0, HOST_DST = 64'h300002fc0;
    localparam int WATCHDOG = 12000;
    bit clk, dclk, pclk;
    always #5 clk = !clk;
    always #3.5 dclk = !dclk;
    always #6.5 pclk = !pclk;
    bit rst = 1, drst = 1, prst = 1;
    bit reg_read, reg_write;
    logic [17:0] reg_addr;
    logic [63:0] reg_wdata;
    wire [63:0] reg_rdata;
    wire reg_rvalid;
    wire [31:0] role_id, role_version, role_status;
    bit amm_ready, amm_readdatavalid;
    logic [511:0] amm_readdata;
    wire amm_read, amm_write;
    wire [25:0] amm_address;
    wire [511:0] amm_writedata;
    wire [6:0] amm_burstcount;
    wire [63:0] amm_byteenable;

    bit rdack, wrack, rdata_en, wdata_en, wrdone;
    logic [255:0] rdata;
    wire rdreq, wrreq, rfull;
    wire [25:0] rdbytes, wrbytes;
    wire [63:0] rdaddr, wraddr;
    wire [255:0] wdata;
    wire cmd_valid, cmd_write, cmd_ready, cpl_valid, cpl_error, cpl_ready, role_abort;
    wire tx_valid, tx_last, tx_ready, rx_valid, rx_last, rx_ready;
    wire [63:0] cmd_addr;
    wire [25:0] cmd_bytes;
    wire [127:0] tx_data, rx_data;
    wire [15:0] tx_keep, rx_keep;
    bit accelerate_watchdog;

    if (N == 256) begin : platform
    SoftShell dut (
        .pcie_refclk(pclk), .pcie_pinrst_n(!prst), .nic_refclk(1'b0), .tor_refclk(1'b0),
        .clk_100(clk), .rst_100(rst), .role_id_out(role_id), .role_version_out(role_version),
        .role_status_out(role_status),
        .aslregA_read_in(reg_read), .aslregA_write_in(reg_write), .aslregA_addr_in(reg_addr),
        .aslregA_wrdata_in(reg_wdata), .aslregA_rddata_out(reg_rdata), .aslregA_rdvalid_out(reg_rvalid),
        .aslregB_read_in(1'b0), .aslregB_write_in(1'b0), .aslregB_addr_in('0), .aslregB_wrdata_in('0),
        .shellreg_rddata_in('0), .shellreg_rdvalid_in(1'b0), .asl_network_active_in(1'b0),
        .nic_clk(1'b0), .nic_rst(1'b1), .tor_clk(1'b0), .tor_rst(1'b1), .nic_rx_in('0), .tor_rx_in('0),
        .nic_rx_valid_in(1'b0), .nic_rx_error_in(1'b0), .nic_rx_fcs_error_in(1'b0), .nic_rx_fcs_valid_in(1'b0),
        .tor_rx_valid_in(1'b0), .tor_rx_error_in(1'b0), .tor_rx_fcs_error_in(1'b0), .tor_rx_fcs_valid_in(1'b0),
        .nic_tx_ready_in(1'b0), .tor_tx_ready_in(1'b0),
        .ammA_clk(dclk), .ammA_rst(drst), .ammA_ready_in(amm_ready),
        .ammA_read_out(amm_read), .ammA_write_out(amm_write), .ammA_address_out(amm_address),
        .ammA_readdata_in(amm_readdata), .ammA_writedata_out(amm_writedata),
        .ammA_burstcount_out(amm_burstcount), .ammA_byteenable_out(amm_byteenable),
        .ammA_readdatavalid_in(amm_readdatavalid),
        .ammB_clk(dclk), .ammB_rst(drst), .ammB_ready_in(1'b0),
        .ammB_readdata_in('0), .ammB_readdatavalid_in(1'b0),
        .pcieA_clk(pclk), .pcieA_rst(prst), .pcieB_clk(pclk), .pcieB_rst(prst),
        .pcieA_intack_in(1'b0), .pcieB_intack_in(1'b0), .pcieA_intmax_in('0), .pcieB_intmax_in('0),
        .pcieA_intaux_read_in(1'b0), .pcieB_intaux_read_in(1'b0),
        .pcieA_wrreq_out(wrreq), .pcieA_wrack_in(wrack), .pcieA_wrbytes_out(wrbytes),
        .pcieA_wraddr_out(wraddr), .pcieA_wrdata_out(wdata), .pcieA_wrdata_rden_in(wdata_en),
        .pcieA_wrdone_in(wrdone), .pcieA_rdreq_out(rdreq), .pcieA_rdack_in(rdack),
        .pcieA_rdbytes_out(rdbytes), .pcieA_rdaddr_out(rdaddr), .pcieA_rddata_in(rdata),
        .pcieA_rddata_wren_in(rdata_en), .pcieA_rddata_afull_out(rfull),
        .pcieB_wrack_in(1'b0), .pcieB_wrdata_rden_in(1'b0), .pcieB_wrdone_in(1'b0),
        .pcieB_rdack_in(1'b0), .pcieB_rddata_in('0), .pcieB_rddata_wren_in(1'b0)
    );
    assign {cmd_valid,cmd_write,cmd_ready,cmd_addr,cmd_bytes} =
        {dut.cmd_valid,dut.cmd_write,dut.cmd_ready,dut.cmd_addr,dut.cmd_bytes};
    assign {cpl_valid,cpl_error,cpl_ready,role_abort} = {dut.cpl_valid,dut.cpl_error,dut.cpl_ready,dut.role_abort};
    assign {tx_valid,tx_last,tx_ready,tx_data,tx_keep} = {dut.tx_valid,dut.tx_last,dut.tx_ready,dut.tx_data,dut.tx_keep};
    assign {rx_valid,rx_last,rx_ready,rx_data,rx_keep} = {dut.rx_valid,dut.rx_last,dut.rx_ready,dut.rx_data,dut.rx_keep};
    // Keep the production watchdog parameter and preload only elapsed time.
    always @(negedge clk)
        if (accelerate_watchdog) dut.role.billet.watchdog <= 24'hff_fff0;

    end else begin : short_frames
        // The shipping shell fixes N=256. Exercise unreachable short tails by
        // composing the same role and vendor-FIFO CDC at smaller legal sizes.
        vulcan_role #(.N_POINTS(N)) role (
            .clk(clk), .reset(rst), .reg_read(reg_read), .reg_write(reg_write),
            .reg_addr(reg_addr), .reg_wdata(reg_wdata), .reg_rdata(reg_rdata), .reg_rvalid(reg_rvalid),
            .ddr_clk(dclk), .ddr_reset(drst),
            .dma_cmd_valid(cmd_valid), .dma_cmd_write(cmd_write), .dma_cmd_ready(cmd_ready),
            .dma_cmd_addr(cmd_addr), .dma_cmd_bytes(cmd_bytes),
            .dma_cpl_valid(cpl_valid), .dma_cpl_error(cpl_error), .dma_cpl_ready(cpl_ready), .dma_abort(role_abort),
            .dma_tx_valid(tx_valid), .dma_tx_last(tx_last), .dma_tx_ready(tx_ready), .dma_tx_data(tx_data), .dma_tx_keep(tx_keep),
            .dma_rx_valid(rx_valid), .dma_rx_last(rx_last), .dma_rx_ready(rx_ready), .dma_rx_data(rx_data), .dma_rx_keep(rx_keep),
            .*
        );
        vulcan_longspeak_dma_cdc bridge (
            .pcie_clk(pclk), .pcie_rst(prst), .role_clk(clk), .role_rst(rst),
            .pcie_rdreq(rdreq), .pcie_rdack(rdack), .pcie_rdaddr(rdaddr), .pcie_rdbytes(rdbytes),
            .pcie_rddata(rdata), .pcie_rddata_wren(rdata_en), .pcie_rddata_afull(rfull),
            .pcie_wrreq(wrreq), .pcie_wrack(wrack), .pcie_wraddr(wraddr), .pcie_wrbytes(wrbytes),
            .pcie_wrdata(wdata), .pcie_wrdata_rden(wdata_en), .pcie_wrdone(wrdone), .*
        );
    end

    logic [31:0] samples [N], expected [N];
    logic [511:0] source [B], destination [B];
    int dd_mode = -1;
    int dreads, dwrites, immediate, delayed, ddr_stalls, dcycle, ccycle;
    int due;
    bit hold_ddr, block_write, dhad_stall;
    logic [511:0] pending;
    logic [610:0] dheld;
    wire [610:0] dpayload = {amm_read, amm_write, amm_address, amm_writedata, amm_burstcount, amm_byteenable};

    function automatic logic [511:0] read_ddr(input int addr);
        if (addr >= int'(DDR_SRC/64) && addr < int'(DDR_SRC/64)+B) return source[addr-int'(DDR_SRC/64)];
        if (addr >= int'(DDR_DST/64) && addr < int'(DDR_DST/64)+B) return destination[addr-int'(DDR_DST/64)];
        // Address rejection belongs to the accepted-request scoreboard.
        return {16{32'hbad0_bad0}};
    endfunction

    function automatic logic [511:0] line(input bit result, input int start);
        logic [511:0] result_line = '0;
        for (int i = 0; i < 16; i++)
            if (start+i < N) result_line[32*i +: 32] = result ? expected[start+i] : samples[start+i];
        return result_line;
    endfunction

    always @(negedge dclk) begin
        amm_ready = !drst && dcycle % 4 >= 2 && (!(amm_read || amm_write) || dhad_stall) &&
                    !(block_write && amm_write && int'(amm_address) >= int'(DDR_DST/64));
        amm_readdatavalid = !drst && !hold_ddr &&
            ((due != 0 && dcycle >= due) ||
             (due == 0 && amm_read && amm_ready && !dreads[0]));
        if (amm_readdatavalid) amm_readdata = due != 0 ? pending : read_ddr(int'(amm_address));
        else amm_readdata = {16{32'hcafe_d00d}};
    end

    always @(posedge dclk) begin
        int address, start;
        dcycle++;
        if (drst) begin
            due = 0;
            dhad_stall = 0;
        end else begin
            if (dhad_stall && ({amm_read, amm_write, amm_address, amm_burstcount, amm_byteenable} !==
                {dheld[610:583], dheld[70:0]} || (amm_write && amm_writedata !== dheld[582:71])))
                $fatal(1, "SHELL_PROTOCOL DDR N=%0d command changed while stalled", N);
            dhad_stall = (amm_read || amm_write) && !amm_ready;
            if (dhad_stall) begin
                dheld = dpayload;
                ddr_stalls++;
            end
            if (amm_read || amm_write) begin
                if (dd_mode <= 0 || (amm_read && amm_write) || amm_burstcount != 1 || amm_byteenable !== '1)
                    $fatal(1, "SHELL_PROTOCOL DDR N=%0d mode=%0d rd/wr=%b/%b burst=%0d enables=%h",
                           N, dd_mode, amm_read, amm_write, amm_burstcount, amm_byteenable);
            end
            if (amm_read && amm_ready) begin
                start = dreads < B ? int'(DDR_SRC/64) : int'(DDR_DST/64)-B;
                if (due != 0 || dreads >= B*dd_mode || int'(amm_address) != start+dreads)
                    $fatal(1, "SHELL_PROTOCOL DDR N=%0d read index=%0d observed=%h expected=%h",
                           N, dreads, amm_address, start+dreads);
                if (amm_readdatavalid) immediate++;
                else begin
                    pending = read_ddr(int'(amm_address));
                    due = dcycle + 3;
                end
                dreads++;
            end else if (amm_readdatavalid) begin
                if (due == 0) $fatal(1, "SHELL_PROTOCOL DDR unsolicited test response");
                due = 0;
                delayed++;
            end
            if (amm_write && amm_ready) begin
                address = int'(amm_address);
                if (dd_mode == 2 && dwrites < B) begin
                    if (address != int'(DDR_SRC/64)+dwrites || amm_writedata !== line(0, 16*dwrites))
                        $fatal(1, "SHELL_NUMERIC DDR input packing/address N=%0d beat=%0d address=%h actual=%h expected=%h",
                               N, dwrites, address, amm_writedata, line(0, 16*dwrites));
                    source[dwrites] = amm_writedata;
                end else begin
                    start = dwrites - (dd_mode == 2 ? B : 0);
                    if (start < 0 || start >= B || address != int'(DDR_DST/64)+start ||
                        amm_writedata !== line(1, 16*start))
                        $fatal(1, "SHELL_NUMERIC DDR output packing/address N=%0d beat=%0d address=%h actual=%h expected=%h",
                               N, start, address, amm_writedata, line(1, 16*start));
                    destination[start] = amm_writedata;
                end
                dwrites++;
            end
        end
    end

    function automatic int chunk(input logic [63:0] addr, input int offset);
        int page, remaining;
        page = 4096 - ((int'(addr) + offset) & 4095);
        remaining = BYTES - offset;
        if (remaining > 128) remaining = 128;
        return (page < remaining) ? page : remaining;
    endfunction

    function automatic logic [255:0] packet(input bit result, input int offset, input int count);
        logic [255:0] data;
        data = result ? '0 : {8{32'hdead_beef}};
        for (int j = 0; j < count/4; j++)
            data[j*32 +:32] = result ? expected[offset/4+j] : samples[offset/4+j];
        return data;
    endfunction

    int pcycle, pr_offset, pw_offset, pr_left, pw_left, pending_done;
    int preads, pwrites, pr_cmds, pw_cmds, pdones;
    bit hold_read, hold_done, fault_read, fault_issued;
    bit rhad_stall, whad_stall;
    logic [89:0] rheld, wheld;

    always @(negedge pclk) begin
        rdack = 0;
        wrack = 0;
        rdata_en = 0;
        wdata_en = 0;
        wrdone = 0;
        if (!prst) begin
            rdack = rdreq && pcycle % 4 == 2;
            wrack = wrreq && pcycle % 5 == 3;
            rdata_en = (pr_left > 0 || rdack) && !rfull && !hold_read && pcycle % 3 != 1;
            if (rdata_en)
                rdata = packet(0, pr_offset, (rdack ? int'(rdbytes) : pr_left) < 32 ?
                               (rdack ? int'(rdbytes) : pr_left) : 32);
            wdata_en = (pw_left > 0 || wrack) && pcycle % 3 != 2;
            wrdone = (pending_done > 0 && pcycle >= pending_done ||
                     (wdata_en && (wrack ? int'(wrbytes) : pw_left) <= 32 && pw_cmds % 2 == 1));
            if (hold_done && (pw_offset == BYTES ||
                (pw_left > 0 && pw_offset + pw_left == BYTES) ||
                (wrack && pw_offset + int'(wrbytes) == BYTES))) wrdone = 0;
            if (fault_read && pr_left > 0 && !fault_issued)
                rdack = 1; // Deliberate second native ACK while in RX_DATA.
        end
    end

    always @(posedge pclk) begin
        int actual;
        pcycle++;
        if (prst) begin
            {pr_left, pw_left, pending_done} = '0;
            {rhad_stall, whad_stall} = '0;
        end else begin
            if (rhad_stall && (!rdreq || {rdaddr, rdbytes} !== rheld) ||
                whad_stall && (!wrreq || {wraddr, wrbytes} !== wheld))
                $fatal(1, "SHELL_PROTOCOL PCIe request changed before native ACK N=%0d", N);
            rhad_stall = rdreq && !rdack;
            whad_stall = wrreq && !wrack;
            rheld = {rdaddr, rdbytes};
            wheld = {wraddr, wrbytes};
            if (rdack && rdreq) begin
                if (dd_mode != 2 || pr_left != 0 || rdaddr != HOST_SRC+64'(pr_offset) ||
                    int'(rdbytes) != chunk(HOST_SRC, pr_offset) || rdbytes == 0)
                    $fatal(1, "SHELL_PROTOCOL PCIe N=%0d read address=%h length=%0d offset=%0d",
                           N, rdaddr, rdbytes, pr_offset);
                pr_left = int'(rdbytes);
                pr_cmds++;
            end else if (rdack && !rdreq) begin
                if (!fault_read || fault_issued) $fatal(1, "SHELL_INPUT spurious model ACK");
                fault_issued = 1;
            end
            if (rdata_en) begin
                actual = pr_left < 32 ? pr_left : 32;
                pr_offset += actual;
                pr_left -= actual;
                preads++;
            end
            if (wrack) begin
                if (dd_mode != 2 || pw_left != 0 || pending_done != 0 || wraddr != HOST_DST+64'(pw_offset) ||
                    int'(wrbytes) != chunk(HOST_DST, pw_offset) || wrbytes == 0)
                    $fatal(1, "SHELL_PROTOCOL PCIe N=%0d write address=%h length=%0d offset=%0d",
                           N, wraddr, wrbytes, pw_offset);
                pw_left = int'(wrbytes);
                pw_cmds++;
            end
            if (wdata_en) begin
                actual = pw_left < 32 ? pw_left : 32;
                if (wdata !== packet(1, pw_offset, actual))
                    $fatal(1, "SHELL_NUMERIC PCIe N=%0d offset=%0d actual=%h expected=%h",
                           N, pw_offset, wdata, packet(1, pw_offset, actual));
                pw_offset += actual;
                pw_left -= actual;
                pwrites++;
                if (pw_left == 0 && !wrdone) pending_done = pcycle + 6;
            end
            if (wrdone) begin
                pending_done = 0;
                pdones++;
            end
        end
    end

    int role_left, role_read, role_write, role_completions, tx_halves, rx_halves;
    bit active_write;
    task automatic stream_score(input bit sending, input logic [15:0] keep, input bit last,
                                input logic [127:0] payload);
        int offset, count;
        logic [127:0] data;
        count = role_left < 16 ? role_left : 16;
        offset = sending ? role_write : role_read;
        data = 128'(packet(sending, offset, count));
        for (int j = count; j < 16; j++) data[8*j +: 8] = 0;
        if (count <= 0 || sending != active_write || keep !== (16'hffff >> (16-count)) ||
            last !== (role_left <= 16) || payload !== data)
            $fatal(1, "SHELL_PROTOCOL stream N=%0d tx=%b offset=%0d count=%0d keep=%h last=%b data=%h expected=%h",
                   N, sending, offset, count, keep, last, payload, data);
        role_left -= count;
        if (sending) begin
            role_write += count;
            tx_halves++;
        end else begin
            role_read += count;
            rx_halves++;
        end
    endtask

    always @(posedge clk) begin
        bit read_requested;
        ccycle++;
        if (!cpl_ready) $fatal(1, "SHELL_PROTOCOL completion ready gated by abort/reset");
        if (!rst && !role_abort) begin
            if (cmd_valid && cmd_ready) begin
                if (dd_mode != 2 || role_left != 0 ||
                    int'(cmd_bytes) != (cmd_write ? chunk(HOST_DST, role_write) : chunk(HOST_SRC, role_read)))
                    $fatal(1, "SHELL_PROTOCOL DMA command N=%0d length or command overlapped data", N);
                active_write = cmd_write;
                if (cmd_addr != (active_write ? HOST_DST+64'(role_write) : HOST_SRC+64'(role_read)))
                    $fatal(1, "SHELL_PROTOCOL DMA command N=%0d address", N);
                role_left = int'(cmd_bytes);
            end
            if (rx_valid && rx_ready) stream_score(0, rx_keep, rx_last, rx_data);
            if (tx_valid && tx_ready) stream_score(1, tx_keep, tx_last, tx_data);
        end
        if (cpl_valid && cpl_ready && !cpl_error) role_completions++;
        read_requested = reg_read && !rst;
        #0.001;
        if (reg_rvalid !== read_requested || (!reg_rvalid && reg_rdata !== '0))
            $fatal(1, "SHELL_PROTOCOL SoftReg one registered response per request, zero on idle");
    end

    task automatic csr(input int address, input bit rd, input bit wr, input logic [63:0] w,
                       output logic [63:0] r);
        @(negedge clk);
        reg_addr = 18'(address);
        reg_write = wr;
        reg_read = rd;
        reg_wdata = w;
        @(posedge clk);
        #1;
        r = reg_rdata;
    endtask

    task automatic write_reg(input int address, input logic [63:0] data);
        logic [63:0] unused;
        csr(address, 0, 1, data, unused);
    endtask

    task automatic read_check(input int address, input logic [63:0] wanted);
        logic [63:0] result;
        csr(address, 1, 0, 0, result);
        if (result !== wanted)
            $fatal(1, "SHELL_CSR N=%0d word=%h actual=%h expected=%h", N, address, result, wanted);
    endtask

    task automatic silence;
        @(negedge clk);
        {reg_read, reg_write} = 0;
    endtask

    task automatic settle(input int edges = 36);
        silence();
        repeat (edges) @(posedge clk);
    endtask

    int clamps [16];
    logic [31:0] stimuli [16][N], results [16][N];
    int frame_count, total_clamps, successful_jobs, fd;
    string base, trace;

    task automatic arm(input int mode, input int index);
        logic [63:0] before_write;
        settle();
        dd_mode = mode;
        {dreads,dwrites,immediate,delayed,ddr_stalls} = '0;
        {pr_offset,pw_offset,pr_left,pw_left,pending_done,preads,pwrites,pr_cmds,pw_cmds,pdones} = '0;
        {role_left, role_read, role_write, role_completions, tx_halves, rx_halves} = '0;
        fault_issued = 0;
        for (int j=0; j<N; j++) begin
            samples[j] = stimuli[index][j];
            expected[j] = results[index][j];
        end
        for (int b=0; b<B; b++) begin
            source[b] = mode == 1 ? line(0,16*b) : '0;
            destination[b] = '0;
        end
        write_reg(3, 4);
        write_reg(4, 64'(mode));
        write_reg(5, DDR_SRC);
        write_reg(6, DDR_DST);
        write_reg(7, HOST_SRC);
        write_reg(8, HOST_DST);
        if (mode == 0) begin
            for (int j=0; j<N; j++) write_reg('h1000+j, {32'h5a5a1234,samples[j]});
            csr('h1000+N-1, 1, 1, 64'(samples[N-1] ^ 32'd1), before_write);
            if (before_write !== 64'(samples[N-1]))
                $fatal(1, "SHELL_CSR same-edge staged read did not return pre-write value");
            read_check('h1000+N-1, 64'(samples[N-1] ^ 32'd1));
            write_reg('h1000+N-1, 64'(samples[N-1]));
            read_check('h1000+N-1, 64'(samples[N-1]));
            read_check('h11000+N-1, 0);
        end
    endtask

    task automatic wait_state(input logic [2:0] wanted);
        logic [63:0] st;
        for (int i=0; i<WATCHDOG+400; i++) begin
            csr(2, 1, 0, 0, st);
            if (st[2:0] == wanted) return;
            if (st[1] && wanted != 2)
                $fatal(1, "SHELL_PROTOCOL unexpected success N=%0d mode=%0d wanted=%b", N, dd_mode, wanted);
            if (st[2] && wanted == 2) begin
                csr(10, 1, 0, 0, st);
                $fatal(1, "SHELL_PROTOCOL unexpected job error N=%0d mode=%0d code=%0d", N, dd_mode, st);
            end
        end
        $fatal(1, "SHELL_PROTOCOL N=%0d mode=%0d status timeout actual=%h wanted=%b", N, dd_mode, st, wanted);
    endtask

    task automatic result_check(input int mode, input int index, input int launch);
        logic [63:0] fft_ticks, elapsed;
        localparam logic [63:0] STREAM_TICKS = 64'(N*$clog2(N)+3*N);
        int csr_ticks;
        wait_state(2);
        csr_ticks = ccycle - launch;
        if (dreads != ((mode == 0) ? 0 : B*mode) || dwrites != dreads ||
            (mode == 2 && (pr_offset != BYTES || pw_offset != BYTES ||
             role_write != BYTES || role_read != BYTES || pw_cmds != pdones ||
             role_completions != pr_cmds+pw_cmds || rx_halves*16 < BYTES || tx_halves*16 < BYTES)) ||
            (mode != 2 && (pr_cmds != 0 || pw_cmds != 0)))
            $fatal(1, "SHELL_PROTOCOL completion before all transfers retired N=%0d mode=%0d", N, mode);
        if (mode > 0 && (ddr_stalls == 0 || immediate == 0 || (N == 256 && delayed == 0)))
            $fatal(1, "SHELL_INPUT missing DDR stall/same-edge/delayed coverage N=%0d mode=%0d", N, mode);
        csr(11, 1, 0, 0, fft_ticks);
        csr(20, 1, 0, 0, elapsed);
        if (fft_ticks < STREAM_TICKS || elapsed < fft_ticks || csr_ticks < 1)
            $fatal(1, "SHELL_TELEMETRY N=%0d mode=%0d FFT=%0d elapsed=%0d CSR=%0d",
                   N, mode, fft_ticks, elapsed, csr_ticks);
        // The FFT counter starts at first acceptance, after prefetch priming.
        if (mode == 0 && fft_ticks != STREAM_TICKS)
            $fatal(1, "SHELL_PROTOCOL staged feed bubble N=%0d FFT=%0d expected=%0d",
                   N, fft_ticks, STREAM_TICKS);
        read_check(12, {dwrites,dreads});
        read_check(13, {pwrites,preads});
        total_clamps += clamps[index];
        read_check(15, (64'(total_clamps)<<1) | 64'(total_clamps != 0));
        read_check(21, {32'b0,16'(N),16'(N)});
        for (int j=0; j<4; j++) read_check(16+j, (j<N) ? 64'(expected[j%N]) : 0);
        for (int j=0; j<N; j++) read_check('h2000+j, 64'(expected[j]));
        read_check('h12000, 0);
        successful_jobs++;
        read_check(14, 64'(successful_jobs));
        $display("SHELL_JOB %0d %0d %0d %0d %0d %0d %0d %0d %0d %0d",
                 N, mode, index, fft_ticks, elapsed, csr_ticks, dreads, dwrites, preads, pwrites);
    endtask

    task automatic wait_transport(input bit pcie);
        silence();
        for (int i=0; i<400; i++) begin
            @(negedge clk);
            if (pcie ? (pr_cmds > 0 && pr_left > 0) : (dreads == 1 && due != 0)) return;
        end
        $fatal(1, "SHELL_INPUT did not reach an externally owned %s command", pcie ? "DMA" : "DDR");
    endtask

    task automatic run_job(input int mode, input int index, input bit boundaries = 0);
        int launch;
        arm(mode, index);
        block_write = boundaries;
        hold_done = boundaries;
        write_reg(3, 1);
        launch = ccycle;
        if (boundaries) begin
            write_reg(4, 17);
            write_reg(5, 1);
            write_reg(6, 3);
            write_reg(7, 7);
            write_reg(8, 15);
            silence();
            for (int i=0; i<6000 && !(amm_write && dreads >= B); i++) @(negedge clk);
            if (!amm_write) $fatal(1, "SHELL_INPUT did not reach stalled DDR write");
            repeat (8) read_check(2, 1);
            block_write = 0;
            while (pw_offset < BYTES) begin
                silence();
                if (ccycle-launch > WATCHDOG-500) $fatal(1, "SHELL_INPUT final native write did not finish");
            end
            if (pending_done == 0) $fatal(1, "SHELL_INPUT final PCIe completion already sent");
            repeat (10) read_check(2, 1);
            hold_done = 0;
            $display("SHELL_EVENT descriptor_snapshot");
            $display("SHELL_EVENT completion_hold");
        end
        result_check(mode, index, launch);
    endtask

    task automatic abort_staged_feed(input int index);
        logic [63:0] progress;
        arm(0, index);
        write_reg(3, 1);
        for (int i=0; i<N; i++) begin
            csr(21, 1, 0, 0, progress);
            if (progress[15:0] != 0) break;
        end
        if (progress[63:16] != 0 || progress[15:0] == 0 || progress[15:0] >= 16'(N))
            $fatal(1, "SHELL_INPUT staged abort did not reach a partially loaded frame: %h", progress);
        write_reg(3, 7);
        wait_state(4);
        read_check(10, 9);
        read_check(14, 64'(successful_jobs));
        read_check('h2000, 0);
        total_clamps = 0;
        $display("SHELL_EVENT abort_staged_feed");
    endtask

    task automatic reject(input int address, input logic [63:0] data, input int error_code);
        if (address != 0) write_reg(address, data);
        write_reg(3, 1);
        wait_state(4);
        read_check(10, 64'(error_code));
        write_reg(3, 4);
    endtask

    task automatic errors;
        logic [63:0] value;
        dd_mode = -1;
        reject(0, 0, 10);
        reject(4, 3, 1);
        write_reg(4, 1);
        reject(5, 1, 2);
        reject(5, DDR_DST+64, 3);
        write_reg(5, DDR_SRC);
        write_reg(4, 2);
        reject(7, HOST_SRC+4, 4);
        reject(7, 64'hffff_ffff_ffff_ffe0, 5);
        read_check('h2000, 0);
        csr(4, 1, 1, 0, value);
        if (value != 2) $fatal(1, "SHELL_CSR did not return pre-write value");
        read_check(4, 0);
        read_check('h10000, 0);
        read_check('h11000, 0);
        $display("SHELL_EVENT invalid_descriptors");
    endtask

    task automatic recoveries;
        arm(1, 0);
        hold_ddr = 1;
        write_reg(3, 1);
        wait_transport(0);
        write_reg(3, 7); // Abort wins over clear and start.
        read_check(2, 5);
        read_check(10, 9);
        repeat (8) read_check(2, 5);
        hold_ddr = 0;
        wait_state(4);
        if (dreads != 1 || dwrites != 0) $fatal(1, "SHELL_PROTOCOL abort did not drain DDR");
        $display("SHELL_EVENT abort_ddr");

        arm(1, 0);
        hold_ddr = 1;
        write_reg(3, 1);
        wait_transport(0);
        @(posedge clk);
        #1;
        accelerate_watchdog = 1;
        @(posedge clk);
        #1;
        accelerate_watchdog = 0;
        wait_state(4);
        read_check(10, 11);
        write_reg(3, 1);
        read_check(10, 7);
        hold_ddr = 0;
        settle();
        if (dreads != 1 || dwrites != 0 || due != 0) $fatal(1, "SHELL_PROTOCOL watchdog did not drain DDR");
        read_check('h2000, 0);
        $display("SHELL_EVENT watchdog");

        arm(1, 0);
        hold_ddr = 1;
        write_reg(3, 1);
        wait_transport(0);
        drst = 1;
        settle(12);
        drst = 0;
        hold_ddr = 0;
        wait_state(4);
        read_check(10, 9);
        settle();
        if (dwrites != 0) $fatal(1, "SHELL_PROTOCOL DDR reset reported stale output");
        $display("SHELL_EVENT reset_ddr");

        arm(2, 0);
        hold_read = 1;
        write_reg(3, 1);
        wait_transport(1);
        write_reg(3, 2);
        repeat (10) read_check(2, 5);
        hold_read = 0;
        wait_state(4);
        read_check(10, 9);
        if (pr_cmds != 1 || pw_cmds != 0 || dwrites != 0)
            $fatal(1, "SHELL_PROTOCOL cancelled DMA accepted new commands");
        $display("SHELL_EVENT abort_dma");

        arm(2, 0);
        hold_read = 1;
        write_reg(3, 1);
        wait_transport(1);
        fault_read = 1;
        wait_state(4);
        read_check(10, 6);
        if (!fault_issued || !role_abort || dwrites != 0)
            $fatal(1, "SHELL_PROTOCOL native DMA fault not quarantined");
        write_reg(3, 4);
        write_reg(3, 1);
        read_check(10, 11);
        fault_read = 0;
        prst = 1;
        settle(16);
        prst = 0;
        hold_read = 0;
        settle();
        $display("SHELL_EVENT dma_fault");

        arm(2, 0);
        hold_read = 1;
        write_reg(3, 1);
        wait_transport(1);
        prst = 1;
        settle(14);
        prst = 0;
        hold_read = 0;
        wait_state(4);
        read_check(10, 9);
        if (dwrites != 0 || pw_cmds != 0) $fatal(1, "SHELL_PROTOCOL native reset leaked output");
        $display("SHELL_EVENT reset_dma");
        total_clamps = 0;
    endtask

    initial begin
        int kind, preload, size;
        if (($test$plusargs("power") && N != 256) ||
            ($value$plusargs("size=%d", size) && N != size)) begin
            finished = 1;
        end else begin
            if (AVL_DATA_WIDTH != 512 || AVL_ADDR_WIDTH != 26 || AVL_BE_WIDTH != 64 || AVL_SIZE != 7)
                $fatal(1, "SHELL_INPUT incorrect ECC build geometry");
            if (!$value$plusargs("shell=%s", base)) $fatal(1, "SHELL_INPUT missing stimulus");
            fd = $fopen($sformatf("%s%0d.txt", base, N), "r");
            if (fd == 0 || $fscanf(fd, "%d", frame_count) != 1 || frame_count < 1 || frame_count > 16)
                $fatal(1, "SHELL_INPUT invalid stimulus N=%0d", N);
            for (int f=0; f<frame_count; f++) begin
                if ($fscanf(fd, "%d %d %d", kind, clamps[f], preload) != 3)
                    $fatal(1, "SHELL_INPUT truncated frame header");
                for (int i=0; i<N; i++)
                    if ($fscanf(fd, "%h %h", stimuli[f][i], results[f][i]) != 2)
                        $fatal(1, "SHELL_INPUT truncated frame payload");
            end
            $fclose(fd);
            if (N == 256 && $value$plusargs("trace=%s", trace)) begin
                $dumpfile(trace);
                $dumpvars();
            end
            repeat (12) @(negedge clk);
            {rst,drst,prst} = 0;
            settle();
            read_check(0, MAGIC);
            read_check(1, IDENT);
            read_check(9, 64'(N));
            read_check('h20000, 0);
            if ({role_version,role_id} !== IDENT) $fatal(1, "SHELL_CSR sideband role identity");
            if ($test$plusargs("power")) begin
                run_job(2, frame_count-1);
                $display("SHELL_POWER_PASS 256");
            end else if ($test$plusargs("focus")) begin
                if (N == 256) begin
                    errors();
                    run_job(1, frame_count-1);
                end
                run_job(2, frame_count-1, N == 256);
                if (N == 256) begin
                    recoveries();
                    abort_staged_feed(frame_count-1);
                end
                run_job(0, 0);
                $display("SHELL_FOCUS_PASS %0d", N);
            end else begin
                if (N == 256) errors();
                for (int f=0; f<frame_count; f++) run_job(0, f);
                run_job(1, frame_count-1);
                run_job(2, frame_count-1, N == 256);
                if (N == 256) begin
                    recoveries();
                    run_job(2, 0);
                    run_job(0, 1);
                    abort_staged_feed(frame_count-1);
                    run_job(0, 0);
                end
                $display("SHELL_PASS %0d", N);
            end
            finished = 1;
        end
    end
endmodule

module tb_billet_softshell;
    wire [3:0] finished;
    billet_shell_case #(.N(2)) n2 (.finished(finished[0]));
    billet_shell_case #(.N(4)) n4 (.finished(finished[1]));
    billet_shell_case #(.N(8)) n8 (.finished(finished[2]));
    billet_shell_case n256 (.finished(finished[3]));
    initial begin
        wait (&finished);
        $finish;
    end
    initial #10000000 $fatal(1, "SHELL_PROTOCOL test timeout");
endmodule

module tb_billet_softshell_only;
    wire finished;
    billet_shell_case n256 (.finished(finished));
    initial begin
        wait (finished);
        $finish;
    end
    initial #10000000 $fatal(1, "SHELL_PROTOCOL test timeout");
endmodule
