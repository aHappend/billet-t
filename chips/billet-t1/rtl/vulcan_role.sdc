# The platform creates clk_100 and the EMIF clock. Cut only the asynchronous
# endpoints owned by this role; leave the second synchronizer stages timed.
set billet_role {*Role_BilletT1:billet}
foreach {source sink} {
    {ready_ddr}        {ready_csr[0]}
    {quiet_ddr}        {quiet_csr[0]}
    {abort_ddr[1]}     {abort_ack_csr[0]}
    {abort_hold}       {abort_ddr[0]}
    {dma_job_lost}     {dma_lost_ddr[0]}
} {
    set src [get_registers -nowarn "${billet_role}|${source}"]
    set dst [get_registers -nowarn "${billet_role}|${sink}"]
    if {[get_collection_size $src] != 1 || [get_collection_size $dst] != 1} {
        error "Missing or ambiguous Billet synchronizer: $source -> $sink"
    }
    set_false_path -from $src -to $dst
}

# Each mailbox holds data through the round-trip acknowledgement. The
# destination captures after two synchronizer stages, so the 5 ns net bound
# budgets routing without assuming any phase relationship between clocks.
foreach mailbox {descriptor_mailbox status_mailbox dma_request_mailbox dma_result_mailbox} {
    set mb "${billet_role}|billet_t1_mailbox:${mailbox}"
    foreach {source sink} {
        {request_toggle} {req_sync[0]}
        {ack_toggle}     {ack_sync[0]}
        {src_hold*}      {dst_data*}
    } {
        set src [get_registers -nowarn "${mb}|${source}"]
        set dst [get_registers -nowarn "${mb}|${sink}"]
        if {[get_collection_size $src] == 0 || [get_collection_size $dst] == 0} {
            error "Missing Billet mailbox endpoints: $mailbox $source -> $sink"
        }
        if {$source eq "src_hold*"} {
            set_net_delay -max -from $src -to $dst 5.0
        }
        set_false_path -from $src -to $dst
    }
}

# Raw reset only enters the asynchronous clear pins of the release chains.
# Their locally synchronized outputs and downstream reset release are timed.
foreach chain {csr_reset fft_reset csr_link_reset ddr_link_reset} {
    set clears [get_pins -compatibility_mode -nowarn \
        "${billet_role}|billet_t1_reset_sync:${chain}|release_sync*|clrn"]
    if {[get_collection_size $clears] != 2} {
        error "Missing Billet reset-release clear pins: $chain"
    }
    set_false_path -to $clears
}
unset billet_role
