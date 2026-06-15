# Wireguard

> -----------

import {ArgTableRow} from '@site/src/components/common';
import {ArgTable} from '@site/src/components/common';

-----------

## interface/wireguard
**Type:** Directory

<ArgTable c1="Flag" c2="Name" c3="Description">
<ArgTableRow arg="X" typ="disabled">disabled</ArgTableRow>
<ArgTableRow arg="R" typ="running">running</ArgTableRow>
</ArgTable>

<ArgTable c1="Argument" c2="Type" c3="Description">
<ArgTableRow arg="name" typ="string"></ArgTableRow>
<ArgTableRow arg="mtu" typ="num"></ArgTableRow>
<ArgTableRow arg="listen-port" typ="num"></ArgTableRow>
<ArgTableRow arg="private-key" typ="string"></ArgTableRow>
<ArgTableRow arg="vrf" typ="enum"></ArgTableRow>
</ArgTable>

<ArgTable c1="Read-only Argument" c2="Type" c3="Description">
<ArgTableRow arg="public-key" typ="string"></ArgTableRow>
</ArgTable>

### interface/wireguard/peers
**Type:** Directory

<ArgTable c1="Flag" c2="Name" c3="Description">
<ArgTableRow arg="X" typ="disabled">disabled</ArgTableRow>
<ArgTableRow arg="D" typ="dynamic">dynamic</ArgTableRow>
</ArgTable>

<ArgTable c1="Argument" c2="Type" c3="Description">
<ArgTableRow arg="interface" typ="iface_enum" mandatory="1"></ArgTableRow>
<ArgTableRow arg="name" typ="string"></ArgTableRow>
<ArgTableRow arg="public-key" typ="string"></ArgTableRow>
<ArgTableRow arg="private-key" typ="alt { enum (none | auto) { none:0, auto:1 }
, string
 }"></ArgTableRow>
<ArgTableRow arg="endpoint-address" typ="address (flags=46D)"></ArgTableRow>
<ArgTableRow arg="endpoint-port" typ="num"></ArgTableRow>
<ArgTableRow arg="allowed-address" typ="multi { address (flags=46/)
 }" mandatory="1"></ArgTableRow>
<ArgTableRow arg="preshared-key" typ="alt { enum (none | auto) { none:0, auto:1 }
, string
 }"></ArgTableRow>
<ArgTableRow arg="persistent-keepalive" typ="time"></ArgTableRow>
<ArgTableRow arg="client-address" typ="multi { address (flags=46/)
 }"></ArgTableRow>
<ArgTableRow arg="client-dns" typ="multi { address (flags=46)
 }"></ArgTableRow>
<ArgTableRow arg="client-endpoint" typ="address (flags=46D)"></ArgTableRow>
<ArgTableRow arg="client-keepalive" typ="time"></ArgTableRow>
<ArgTableRow arg="client-listen-port" typ="num"></ArgTableRow>
<ArgTableRow arg="client-allowed-address" typ="multi { address (flags=46/)
 }"></ArgTableRow>
<ArgTableRow arg="responder" typ="bool"></ArgTableRow>
</ArgTable>

<ArgTable c1="Read-only Argument" c2="Type" c3="Description">
<ArgTableRow arg="current-endpoint-address" typ="address (flags=46)"></ArgTableRow>
<ArgTableRow arg="current-endpoint-port" typ="num"></ArgTableRow>
<ArgTableRow arg="rx" typ="num"></ArgTableRow>
<ArgTableRow arg="tx" typ="num"></ArgTableRow>
<ArgTableRow arg="last-handshake" typ="time"></ArgTableRow>
</ArgTable>

#### interface/wireguard/peers/show-client-config
**Type:** Command

<ArgTable c1="Argument" c2="Type" c3="Description">
<ArgTableRow arg="file" typ="file {  }"></ArgTableRow>
</ArgTable>

<ArgTable c1="Read-only Argument" c2="Type" c3="Description">
<ArgTableRow arg="conf" typ="string"></ArgTableRow>
<ArgTableRow arg="qr" typ="pic"></ArgTableRow>
</ArgTable>

### interface/wireguard/wg-export
**Type:** Command

<ArgTable c1="Argument" c2="Type" c3="Description">
<ArgTableRow arg="file" typ="file"></ArgTableRow>
</ArgTable>

### interface/wireguard/wg-import
**Type:** Command

<ArgTable c1="Argument" c2="Type" c3="Description">
<ArgTableRow arg="config-file" typ="file"></ArgTableRow>
<ArgTableRow arg="config-string" typ="string"></ArgTableRow>
</ArgTable>
