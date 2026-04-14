// SPDX-License-Identifier: Apache-2.0
/* -*- P4_16 -*- */
#include <core.p4>
#include <v1model.p4>

#define FLOWLET_SIZE    8192
#define FLOWLET_TIMEOUT 48w200000
#define NUM_PATHS       2

header ethernet_t {
    bit<48> dstAddr;
    bit<48> srcAddr;
    bit<16> etherType;
}

header ipv4_t {
    bit<4>  version;
    bit<4>  ihl;
    bit<8>  diffserv;
    bit<16> totalLen;
    bit<16> identification;
    bit<3>  flags;
    bit<13> fragOffset;
    bit<8>  ttl;
    bit<8>  protocol;
    bit<16> hdrChecksum;
    bit<32> srcAddr;
    bit<32> dstAddr;
}

header tcp_t {
    bit<16> srcPort;
    bit<16> dstPort;
    bit<32> seqNo;
    bit<32> ackNo;
    bit<4>  dataOffset;
    bit<3>  res;
    bit<3>  ecn;
    bit<6>  ctrl;
    bit<16> window;
    bit<16> checksum;
    bit<16> urgentPtr;
}

struct metadata {
    bit<14> ecmp_select;
    bit<14> flowlet_register_index;
    bit<16> flowlet_id;
    bit<48> flowlet_last_stamp;
    bit<48> flowlet_time_diff;
    bit<19> cong_path0;
    bit<19> cong_path1;
}

struct headers {
    ethernet_t ethernet;
    ipv4_t     ipv4;
    tcp_t      tcp;
}

register<bit<16>>(FLOWLET_SIZE) flowlet_to_id;
register<bit<48>>(FLOWLET_SIZE) flowlet_time_stamp;
register<bit<19>>(NUM_PATHS)    congestion_reg;

parser MyParser(packet_in packet,
                out headers hdr,
                inout metadata meta,
                inout standard_metadata_t standard_metadata) {
    state start { transition parse_ethernet; }
    state parse_ethernet {
        packet.extract(hdr.ethernet);
        transition select(hdr.ethernet.etherType) {
            0x800:   parse_ipv4;
            default: accept;
        }
    }
    state parse_ipv4 {
        packet.extract(hdr.ipv4);
        transition select(hdr.ipv4.protocol) {
            6:       parse_tcp;
            default: accept;
        }
    }
    state parse_tcp { packet.extract(hdr.tcp); transition accept; }
}

control MyVerifyChecksum(inout headers hdr, inout metadata meta) { apply { } }

control MyIngress(inout headers hdr,
                  inout metadata meta,
                  inout standard_metadata_t standard_metadata) {

    action drop() { mark_to_drop(standard_metadata); }

    action set_ecmp_select(bit<16> ecmp_base, bit<32> ecmp_count) {
        hash(meta.ecmp_select, HashAlgorithm.crc16, ecmp_base,
             { hdr.ipv4.srcAddr, hdr.ipv4.dstAddr, hdr.ipv4.protocol,
               hdr.tcp.srcPort,  hdr.tcp.dstPort },
             ecmp_count);
    }

    action set_nhop(bit<48> nhop_dmac, bit<32> nhop_ipv4, bit<9> port) {
        hdr.ethernet.dstAddr          = nhop_dmac;
        hdr.ipv4.dstAddr              = nhop_ipv4;
        standard_metadata.egress_spec = port;
        hdr.ipv4.ttl                  = hdr.ipv4.ttl - 1;
    }

    action read_flowlet_registers() {
        hash(meta.flowlet_register_index,
             HashAlgorithm.crc16,
             (bit<1>)0,
             { hdr.ipv4.srcAddr, hdr.ipv4.dstAddr, hdr.ipv4.protocol,
               hdr.tcp.srcPort,  hdr.tcp.dstPort },
             (bit<14>)FLOWLET_SIZE);
        flowlet_to_id.read(meta.flowlet_id,
                           (bit<32>)meta.flowlet_register_index);
        flowlet_time_stamp.read(meta.flowlet_last_stamp,
                                (bit<32>)meta.flowlet_register_index);
        flowlet_time_stamp.write((bit<32>)meta.flowlet_register_index,
                                 standard_metadata.ingress_global_timestamp);
        meta.flowlet_time_diff = standard_metadata.ingress_global_timestamp
                                 - meta.flowlet_last_stamp;
    }

    action update_flowlet_id() {
        congestion_reg.read(meta.cong_path0, 0);
        congestion_reg.read(meta.cong_path1, 1);
        if (meta.cong_path0 <= meta.cong_path1) {
            meta.flowlet_id = 0;
        } else {
            meta.flowlet_id = 1;
        }
        flowlet_to_id.write((bit<32>)meta.flowlet_register_index,
                            meta.flowlet_id);
    }

    //single CONGA nhop table keyed on flowlet_id
    action set_conga_nhop(bit<48> nhop_dmac, bit<32> nhop_ipv4, bit<9> port) {
        hdr.ethernet.dstAddr          = nhop_dmac;
        hdr.ipv4.dstAddr              = nhop_ipv4;
        standard_metadata.egress_spec = port;
        hdr.ipv4.ttl                  = hdr.ipv4.ttl - 1;
    }

    table conga_nhop {
        key     = { meta.flowlet_id: exact; }
        actions  = { set_conga_nhop; drop; }
        size    = 2;
        default_action = drop();
    }

    //which destinations get CONGA-Flow treatment
    action use_conga() { }
    table conga_check {
        key    = { hdr.ipv4.dstAddr: lpm; }
        actions = { use_conga; NoAction; }
        size   = 16;
        default_action = NoAction();
    }

    table ecmp_group {
        key     = { hdr.ipv4.dstAddr: lpm; }
        actions  = { drop; set_ecmp_select; }
        size    = 1024;
    }

    table ecmp_nhop {
        key     = { meta.ecmp_select: exact; }
        actions  = { drop; set_nhop; }
        size    = 256;
    }

    apply {
        if (hdr.ipv4.isValid() && hdr.ipv4.ttl > 0) {
            if (conga_check.apply().hit) {
                read_flowlet_registers();
                if (meta.flowlet_time_diff > FLOWLET_TIMEOUT) {
                    update_flowlet_id();
                }
                conga_nhop.apply();
            } else {
                if (ecmp_group.apply().hit) {
                    ecmp_nhop.apply();
                }
            }
        }
    }
}

control MyEgress(inout headers hdr,
                 inout metadata meta,
                 inout standard_metadata_t standard_metadata) {

    action rewrite_mac(bit<48> smac) { hdr.ethernet.srcAddr = smac; }
    action drop() { mark_to_drop(standard_metadata); }

    table send_frame {
        key     = { standard_metadata.egress_port: exact; }
        actions  = { rewrite_mac; drop; }
        size    = 256;
    }

    apply {
        send_frame.apply();
        if (standard_metadata.ingress_port == 1) {
            congestion_reg.write(0, (bit<19>)standard_metadata.deq_qdepth);
        }
        if (standard_metadata.ingress_port == 2) {
            congestion_reg.write(1, (bit<19>)standard_metadata.deq_qdepth);
        }
    }
}

control MyComputeChecksum(inout headers hdr, inout metadata meta) {
    apply {
        update_checksum(hdr.ipv4.isValid(),
            { hdr.ipv4.version, hdr.ipv4.ihl, hdr.ipv4.diffserv,
              hdr.ipv4.totalLen, hdr.ipv4.identification, hdr.ipv4.flags,
              hdr.ipv4.fragOffset, hdr.ipv4.ttl, hdr.ipv4.protocol,
              hdr.ipv4.srcAddr, hdr.ipv4.dstAddr },
            hdr.ipv4.hdrChecksum, HashAlgorithm.csum16);
    }
}

control MyDeparser(packet_out packet, in headers hdr) {
    apply {
        packet.emit(hdr.ethernet);
        packet.emit(hdr.ipv4);
        packet.emit(hdr.tcp);
    }
}

V1Switch(MyParser(), MyVerifyChecksum(), MyIngress(),
         MyEgress(), MyComputeChecksum(), MyDeparser()) main;
