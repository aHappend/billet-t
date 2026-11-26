`timescale 1ns/1ps
module bridge;
    reg clk = 0, rst_n = 0;
    reg in_valid = 0, in_last = 0, out_ready = 0;
    reg signed [15:0] in_re = 0, in_im = 0;
    reg [3:0] cfg_log2_n = 4;
    reg cfg_ifft = 0;
    reg [1:0] cfg_scale_mode = 0;
    reg [7:0] cfg_stage_shift_mask = 0;
    wire in_ready, out_valid, out_last, frame_done, overflow_flag;
    wire cfg_error;
    wire signed [15:0] out_re, out_im;
    wire [7:0] out_bin_idx;
    wire [3:0] out_block_exp;
    wire [31:0] saturation_count;
`ifdef REFERENCE
    billet_t1_top dut (
        .clk(clk), .rst_n(rst_n), .in_valid(in_valid), .in_last(in_last),
        .out_ready(out_ready), .in_re(in_re), .in_im(in_im),
        .in_ready(in_ready), .out_valid(out_valid), .out_last(out_last),
        .frame_done(frame_done), .overflow_flag(overflow_flag),
        .out_re(out_re), .out_im(out_im), .out_bin_idx(out_bin_idx),
        .saturation_count(saturation_count)
    );
    assign cfg_error = 0;
    assign out_block_exp = out_valid ? 8 : 0;
`else
    billet_t2_top dut (.*);
`endif
    integer fd, trace, rc, row = 0, i;
    integer inp[0:9];
    reg [31:0] expected[0:11];
    reg [31:0] actual[0:11];
    reg [63:0] held;
    reg stalled = 0;
    reg [4095:0] vectors_path, trace_path;

    task automatic collect;
        begin
            actual[0] = in_ready; actual[1] = out_valid;
            actual[2] = out_last; actual[3] = frame_done;
            actual[4] = overflow_flag; actual[5] = cfg_error;
            actual[6] = {{16{out_re[15]}},out_re};
            actual[7] = {{16{out_im[15]}},out_im};
            actual[8] = out_bin_idx; actual[9] = out_block_exp;
            actual[10] = saturation_count;
            actual[11] = 0;
        end
    endtask
    task automatic reset_check;
        begin
            if ({in_ready,out_valid,out_last,frame_done,overflow_flag,cfg_error,
                 out_re,out_im,out_bin_idx,out_block_exp,saturation_count} !== 0)
                $fatal(1,"RESET_X_OR_NONZERO time=%0t",$time);
        end
    endtask
    task automatic compare;
        begin
            collect();
            for (i=0;i<12;i=i+1)
`ifdef REFERENCE
                // T1 has a different diagnostic-update schedule. Its exact
                // cumulative diagnostics are compared on every valid output.
                if (!((i==4 || i==10) && !out_valid))
`endif
                if (actual[i] !== expected[i])
                    $fatal(1,"MISMATCH row=%0d pin=%0d got=%h expected=%h",
                           row,i,actual[i],expected[i]);
        end
    endtask
    initial begin
        if (!$value$plusargs("vectors=%s",vectors_path) ||
            !$value$plusargs("trace=%s",trace_path)) $fatal(1,"missing paths");
        fd=$fopen(vectors_path,"r"); trace=$fopen(trace_path,"w");
        if (!fd || !trace) $fatal(1,"file open");
        #0; reset_check();
        #1; reset_check();
        #4; clk=1; reset_check(); // Active region at first posedge, before NBA.
        #1; reset_check();
        #4; clk=0; reset_check();
        while (!$feof(fd)) begin
            rc=$fscanf(fd,"%d %d %d %d %d %d %d %d %d %d %h %h %h %h %h %h %h %h %h %h %h %h\n",
                inp[0],inp[1],inp[2],inp[3],inp[4],inp[5],inp[6],inp[7],inp[8],inp[9],
                expected[0],expected[1],expected[2],expected[3],expected[4],expected[5],
                expected[6],expected[7],expected[8],expected[9],expected[10],expected[11]);
            if (rc != 22) begin
                if (rc == -1 && $feof(fd)) begin end
                else $fatal(1,"MALFORMED row=%0d fields=%0d",row,rc);
            end else begin
                rst_n=inp[0]; in_valid=inp[1]; in_last=inp[2];
                out_ready=inp[3]; in_re=inp[4]; in_im=inp[5];
                cfg_log2_n=inp[6]; cfg_ifft=inp[7];
                cfg_scale_mode=inp[8]; cfg_stage_shift_mask=inp[9];
                #1;
                if (!rst_n) reset_check();
                #4;
                if (rst_n && out_valid && out_ready)
                    $fdisplay(trace,"%0d %0d %0d %0d %0d %0d %0d",
                        row,$signed(out_re),$signed(out_im),out_bin_idx,
                        out_last,out_block_exp,saturation_count);
                if (rst_n && stalled &&
                    {out_re,out_im,out_bin_idx,out_last,out_block_exp} !== held)
                    $fatal(1,"STALL row=%0d",row);
                if (rst_n && (^{in_ready,out_valid,out_last,frame_done,
                    overflow_flag,cfg_error,out_re,out_im,out_bin_idx,
                    out_block_exp,saturation_count}) === 1'bx)
                    $fatal(1,"ACTIVE_XZ row=%0d",row);
                stalled=rst_n && out_valid && !out_ready;
                held={out_re,out_im,out_bin_idx,out_last,out_block_exp};
                clk=1;
                if (!rst_n) reset_check();
                #1; compare();
                #4; clk=0; compare();
                row=row+1;
            end
        end
        $fdisplay(trace,"COMPLETE %0d",row);
        $fclose(trace); $fclose(fd);
        $display("COMPARED %0d cycles",row);
        $finish;
    end
endmodule
