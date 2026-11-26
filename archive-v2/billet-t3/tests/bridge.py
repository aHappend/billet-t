"""Generate simulation-only bridges under the selected evidence directory.

All observations are module ports. No hierarchical DUT access, forces, internal
state mirrors, generated RTL dependencies or silent EOF handling are used.
"""
TOP_FIELDS = [
    ("in_ready", 1), ("cfg_error", 1), ("out_valid", 1), ("out_last", 1),
    ("frame_done", 1), ("overflow_flag", 1), ("out_re", 16), ("out_im", 16),
    ("out_power", 32), ("saturation_count", 32), ("out_bin_idx", 8),
    ("out_block_exp", 4), ("out_ch_id", 2), ("frame_done_ch_id", 2)]
BUFFER_FIELDS = [
    ("in_ready", 1), ("cfg_error", 1), ("f_valid", 1), ("f_last", 1),
    ("f_re", 16), ("f_im", 16), ("f_idx", 8), ("f_ch_id", 2),
    ("f_log2_n", 4), ("f_ifft", 1), ("f_scale_mode", 2),
    ("f_stage_shift_mask", 8), ("f_overlap_mode", 1), ("f_window_mode", 2)]


def decode(word, fields):
    if any(c in word.lower() for c in "xz"):
        raise AssertionError("Unknown public output: " + word)
    value = int(word, 16)
    result = {}
    for name, width in reversed(fields):
        result[name] = value & ((1 << width) - 1)
        value >>= width
    assert value == 0
    for name in ("out_re", "out_im", "f_re", "f_im"):
        if name in result and result[name] >= 32768:
            result[name] -= 65536
    return result


def bench(kind, vector_path, trace_path):
    buffer = kind == "buffer"
    fields = BUFFER_FIELDS if buffer else TOP_FIELDS
    packed = "{" + ",".join(name for name, _ in fields) + "}"
    width = sum(w for _, w in fields)
    declarations = "\n".join(
        f"wire [{w-1}:0] {name};" for name, w in fields)
    common_inputs = ["clk", "rst_n", "in_valid", "in_last", "in_re", "in_im",
                     "cfg_log2_n", "cfg_ifft", "cfg_scale_mode",
                     "cfg_stage_shift_mask"]
    if buffer or kind == "top":
        common_inputs += ["ch_id", "cfg_overlap_mode", "cfg_window_mode"]
    module = {"top": "billet_t3_top", "core": "billet_t3_fft_core",
              "reference": "billet_t2_top", "buffer": "billet_t3_channel_buf"}[kind]
    output_names = [name for name, _ in fields]
    extra = ""
    if kind in ("core", "reference"):
        output_names = [n for n in output_names
                        if n not in ("out_power", "out_ch_id", "frame_done_ch_id")]
        extra = ("assign out_power=0; assign out_ch_id=0;"
                 "assign frame_done_ch_id=0;")
    ports = common_inputs + output_names
    ports += ["f_ready"] if buffer else ["out_ready"]
    instance = module + " dut (" + ",".join(f".{n}({n})" for n in ports) + ");"
    valid = "f_valid" if buffer else "out_valid"
    last = "f_last" if buffer else "out_last"
    done = "(f_valid && f_ready && f_last)" if buffer else "frame_done"
    return f"""`timescale 1ns/1ps
module tb;
reg clk, rst_n;
reg in_valid,in_last,out_ready;
reg signed [15:0] in_re,in_im;
reg [1:0] ch_id,cfg_scale_mode,cfg_window_mode;
reg [3:0] cfg_log2_n;
reg cfg_ifft,cfg_overlap_mode;
reg [7:0] cfg_stage_shift_mask;
wire f_ready=out_ready;
{declarations}
{instance}
{extra}
reg [{width-1}:0] before_value;
integer fd,trace,rc,op,count,iv,il,ir,ii,ch,ln,inv,sm,mask,ov,win,ready;
integer cycle=0,command=0,j,observed,guard,hit;
task tick;
begin
    #4;
    before_value={packed};
    if ((^{packed}) === 1'bx) $fatal(1,"PUBLIC_XZ pre cycle=%0d",cycle);
    if (!rst_n && ({packed} !== {width}'d0))
        $fatal(1,"RESET_ACTIVE pre cycle=%0d",cycle);
    clk=1;
    // This observation is in Active, before any nonblocking register updates.
    if (!rst_n && ({packed} !== {width}'d0)) $fatal(1,"RESET_FIRST_POSEDGE");
    #1;
    if ((^{packed}) === 1'bx) $fatal(1,"PUBLIC_XZ post cycle=%0d",cycle);
    if (!rst_n && ({packed} !== {width}'d0)) $fatal(1,"RESET_POST");
    $fdisplay(trace,"%0d %0d %0d %0d %0d %0d %0d %0d %0d %0d %0d %0d %0d %0d %0d %h %h",
        cycle,command,rst_n,in_valid,in_last,$signed(in_re),$signed(in_im),
        ch_id,cfg_log2_n,cfg_ifft,cfg_scale_mode,cfg_stage_shift_mask,
        cfg_overlap_mode,cfg_window_mode,out_ready,before_value,{packed});
    cycle=cycle+1;
    #5; clk=0;
    if (!rst_n && ({packed} !== {width}'d0)) $fatal(1,"RESET_NEGEDGE");
end
endtask
initial begin
    clk=0; rst_n=0; in_valid=0; in_last=0; out_ready=0;
    in_re=0;in_im=0;ch_id=0;cfg_log2_n=4;cfg_ifft=0;
    cfg_scale_mode=0;cfg_stage_shift_mask=0;cfg_overlap_mode=0;cfg_window_mode=0;
    #0;
    if ({packed} !== {width}'d0) $fatal(1,"TIME_ZERO_RESET");
    #1;
    fd=$fopen("{vector_path}","r");trace=$fopen("{trace_path}","w");
    if (!fd || !trace) $fatal(1,"FILE_OPEN");
    // First rising edge is t=5, with reset low since time zero.
    tick;
    while (!$feof(fd)) begin
        rc=$fscanf(fd,"%d %d %d %d %d %d %d %d %d %d %d %d %d %d\\n",
            op,count,iv,il,ir,ii,ch,ln,inv,sm,mask,ov,win,ready);
        if (rc != 14) $fatal(1,"MALFORMED_VECTOR fields=%0d command=%0d",rc,command);
        in_valid=iv;in_last=il;in_re=ir;in_im=ii;ch_id=ch;
        cfg_log2_n=ln;cfg_ifft=inv;cfg_scale_mode=sm;cfg_stage_shift_mask=mask;
        cfg_overlap_mode=ov;cfg_window_mode=win;out_ready=ready;
        #0;
        if (op==4) begin
            rst_n=0;
            #1;
            if ({packed} !== {width}'d0) $fatal(1,"ASYNC_RESET");
            repeat(count) tick;
            rst_n=1;
        end else if (op==7) begin
            rst_n=0;
            #1;
            if ({packed} !== {width}'d0) $fatal(1,"ASYNC_PULSE_ASSERT");
            // A is an asynchronous observation, not a rising-edge cycle.
            $fdisplay(trace,"A %0d 0 %0d %0d %0d %0d %0d %0d %0d %0d %0d %0d %0d %0d %h %h",
                command,in_valid,in_last,$signed(in_re),$signed(in_im),
                ch_id,cfg_log2_n,cfg_ifft,cfg_scale_mode,cfg_stage_shift_mask,
                cfg_overlap_mode,cfg_window_mode,out_ready,{packed},{packed});
            rst_n=1;
            #1;
            if ({packed} !== {width}'h{1 << (width-1):x})
                $fatal(1,"ASYNC_ABORT_WITHOUT_CLOCK");
        end else if (op==0 || op==5) begin
            repeat(count) tick;
        end else if (op==1) begin
            hit=0;guard=0;
            while (!hit) begin
                #1;hit=in_ready;tick;
                guard=guard+1;
                if(guard>2000000) $fatal(1,"NO_INPUT_PROGRESS");
            end
        end else if (op==2) begin
            observed=0;guard=0;
            while(observed<count) begin
                #1;
                if({done}) observed=observed+1;
                tick;guard=guard+1;
                if(guard>2000000) $fatal(1,"NO_COMPLETION_PROGRESS");
            end
        end else if (op==3) begin
            guard=0;
            #1;
            while (!({valid} && (!count || {last}))) begin
                tick;guard=guard+1;
                if(guard>2000000) $fatal(1,"NO_VALID_PROGRESS");
            end
        end else if (op==6) begin
            guard=0;#1;
            while (!({valid} && {last})) begin
                tick;guard=guard+1;
                if(guard>2000000) $fatal(1,"NO_LAST_PROGRESS");
            end
            out_ready=0;
            tick;
        end else $fatal(1,"INVALID_OPCODE");
        command=command+1;
    end
    $fclose(fd);$fclose(trace);
    $display("BRIDGE_COMPLETE commands=%0d cycles=%0d",command,cycle);
    $finish;
end
endmodule
"""
