module billet_t1_twiddle_rom #(
    parameter integer N_POINTS = 256,
    parameter integer LOG2_N = (N_POINTS > 1) ? $clog2(N_POINTS) : 1,
    parameter integer A = (LOG2_N > 0) ? LOG2_N : 1
) (
    input wire [A-1:0] k,
    output wire signed [15:0] w_re, w_im
);
    generate
        if ((N_POINTS >= 2) && (N_POINTS <= 256) &&
            ((N_POINTS & (N_POINTS-1)) == 0) &&
            (LOG2_N == $clog2(N_POINTS)) && (A == LOG2_N)) begin : g_legal
            wire [31:0] table_index = k * (256 / N_POINTS);
            reg [31:0] value;
            always @* begin
                case (table_index[6:0])
                    7'd0: value = 32'h7fff0000;
                    7'd1: value = 32'h7ff6fcdc;
                    7'd2: value = 32'h7fd9f9b8;
                    7'd3: value = 32'h7fa7f695;
                    7'd4: value = 32'h7f62f374;
                    7'd5: value = 32'h7f0af055;
                    7'd6: value = 32'h7e9ded38;
                    7'd7: value = 32'h7e1eea1e;
                    7'd8: value = 32'h7d8ae707;
                    7'd9: value = 32'h7ce4e3f4;
                    7'd10: value = 32'h7c2ae0e6;
                    7'd11: value = 32'h7b5ddddc;
                    7'd12: value = 32'h7a7ddad8;
                    7'd13: value = 32'h798ad7d9;
                    7'd14: value = 32'h7885d4e1;
                    7'd15: value = 32'h776cd1ef;
                    7'd16: value = 32'h7642cf04;
                    7'd17: value = 32'h7505cc21;
                    7'd18: value = 32'h73b6c946;
                    7'd19: value = 32'h7255c673;
                    7'd20: value = 32'h70e3c3a9;
                    7'd21: value = 32'h6f5fc0e9;
                    7'd22: value = 32'h6dcabe32;
                    7'd23: value = 32'h6c24bb85;
                    7'd24: value = 32'h6a6eb8e3;
                    7'd25: value = 32'h68a7b64c;
                    7'd26: value = 32'h66d0b3c0;
                    7'd27: value = 32'h64e9b140;
                    7'd28: value = 32'h62f2aecc;
                    7'd29: value = 32'h60ecac65;
                    7'd30: value = 32'h5ed7aa0a;
                    7'd31: value = 32'h5cb4a7bd;
                    7'd32: value = 32'h5a82a57e;
                    7'd33: value = 32'h5843a34c;
                    7'd34: value = 32'h55f6a129;
                    7'd35: value = 32'h539b9f14;
                    7'd36: value = 32'h51349d0e;
                    7'd37: value = 32'h4ec09b17;
                    7'd38: value = 32'h4c409930;
                    7'd39: value = 32'h49b49759;
                    7'd40: value = 32'h471d9592;
                    7'd41: value = 32'h447b93dc;
                    7'd42: value = 32'h41ce9236;
                    7'd43: value = 32'h3f1790a1;
                    7'd44: value = 32'h3c578f1d;
                    7'd45: value = 32'h398d8dab;
                    7'd46: value = 32'h36ba8c4a;
                    7'd47: value = 32'h33df8afb;
                    7'd48: value = 32'h30fc89be;
                    7'd49: value = 32'h2e118894;
                    7'd50: value = 32'h2b1f877b;
                    7'd51: value = 32'h28278676;
                    7'd52: value = 32'h25288583;
                    7'd53: value = 32'h222484a3;
                    7'd54: value = 32'h1f1a83d6;
                    7'd55: value = 32'h1c0c831c;
                    7'd56: value = 32'h18f98276;
                    7'd57: value = 32'h15e281e2;
                    7'd58: value = 32'h12c88163;
                    7'd59: value = 32'h0fab80f6;
                    7'd60: value = 32'h0c8c809e;
                    7'd61: value = 32'h096b8059;
                    7'd62: value = 32'h06488027;
                    7'd63: value = 32'h0324800a;
                    7'd64: value = 32'h00008000;
                    7'd65: value = 32'hfcdc800a;
                    7'd66: value = 32'hf9b88027;
                    7'd67: value = 32'hf6958059;
                    7'd68: value = 32'hf374809e;
                    7'd69: value = 32'hf05580f6;
                    7'd70: value = 32'hed388163;
                    7'd71: value = 32'hea1e81e2;
                    7'd72: value = 32'he7078276;
                    7'd73: value = 32'he3f4831c;
                    7'd74: value = 32'he0e683d6;
                    7'd75: value = 32'hdddc84a3;
                    7'd76: value = 32'hdad88583;
                    7'd77: value = 32'hd7d98676;
                    7'd78: value = 32'hd4e1877b;
                    7'd79: value = 32'hd1ef8894;
                    7'd80: value = 32'hcf0489be;
                    7'd81: value = 32'hcc218afb;
                    7'd82: value = 32'hc9468c4a;
                    7'd83: value = 32'hc6738dab;
                    7'd84: value = 32'hc3a98f1d;
                    7'd85: value = 32'hc0e990a1;
                    7'd86: value = 32'hbe329236;
                    7'd87: value = 32'hbb8593dc;
                    7'd88: value = 32'hb8e39592;
                    7'd89: value = 32'hb64c9759;
                    7'd90: value = 32'hb3c09930;
                    7'd91: value = 32'hb1409b17;
                    7'd92: value = 32'haecc9d0e;
                    7'd93: value = 32'hac659f14;
                    7'd94: value = 32'haa0aa129;
                    7'd95: value = 32'ha7bda34c;
                    7'd96: value = 32'ha57ea57e;
                    7'd97: value = 32'ha34ca7bd;
                    7'd98: value = 32'ha129aa0a;
                    7'd99: value = 32'h9f14ac65;
                    7'd100: value = 32'h9d0eaecc;
                    7'd101: value = 32'h9b17b140;
                    7'd102: value = 32'h9930b3c0;
                    7'd103: value = 32'h9759b64c;
                    7'd104: value = 32'h9592b8e3;
                    7'd105: value = 32'h93dcbb85;
                    7'd106: value = 32'h9236be32;
                    7'd107: value = 32'h90a1c0e9;
                    7'd108: value = 32'h8f1dc3a9;
                    7'd109: value = 32'h8dabc673;
                    7'd110: value = 32'h8c4ac946;
                    7'd111: value = 32'h8afbcc21;
                    7'd112: value = 32'h89becf04;
                    7'd113: value = 32'h8894d1ef;
                    7'd114: value = 32'h877bd4e1;
                    7'd115: value = 32'h8676d7d9;
                    7'd116: value = 32'h8583dad8;
                    7'd117: value = 32'h84a3dddc;
                    7'd118: value = 32'h83d6e0e6;
                    7'd119: value = 32'h831ce3f4;
                    7'd120: value = 32'h8276e707;
                    7'd121: value = 32'h81e2ea1e;
                    7'd122: value = 32'h8163ed38;
                    7'd123: value = 32'h80f6f055;
                    7'd124: value = 32'h809ef374;
                    7'd125: value = 32'h8059f695;
                    7'd126: value = 32'h8027f9b8;
                    7'd127: value = 32'h800afcdc;
                    default: value = 32'hxxxxxxxx;
                endcase
            end
            assign w_re = value[31:16];
            assign w_im = value[15:0];
        end else begin : g_illegal
            assign w_re = 0;
            assign w_im = 0;
            initial $fatal(1, "PARAMETER ERROR: billet_t1_twiddle_rom requires power-of-two N_POINTS in [2,256] and derived widths");
        end
    endgenerate
endmodule
