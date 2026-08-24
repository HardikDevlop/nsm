# Manual Network Topology Guide

## 1. Objective

Is document ka purpose network ki manual physical aur logical topology banana hai. Isme devices, connections, interfaces, IP addresses aur VLANs ko clearly show kiya jayega.

## 2. Required Information

Topology banane se pehle yeh details collect karein:

- ISP/Internet connection
- Firewall ya edge router
- Core/distribution switch
- Access switches
- Servers, PCs, printers aur access points
- Har device ka hostname aur management IP
- Har link ka source interface aur destination interface
- VLAN ID, subnet aur gateway

## 3. Physical Topology Graph

```text
                         INTERNET / ISP
                                |
                         [Firewall FW-01]
                         WAN: ISP-G0/0
                         LAN: 10.0.0.1/30
                                |
                         [Core Switch CS-01]
                         VLAN 99: 10.0.0.2
                         /                  \
                        /                    \
             [Access Switch AS-01]       [Access Switch AS-02]
             Mgmt: 10.0.0.11              Mgmt: 10.0.0.12
                  |                            |
          +-------+-------+              +-----+-----+
          |       |       |              |           |
       [PC-01] [PC-02] [AP-01]        [Server-01] [Printer-01]
       VLAN 10 VLAN 10 VLAN 20        VLAN 30      VLAN 40
```

## 4. Logical Topology Graph

```text
Firewall FW-01
    |
    +-- VLAN 10: Users       192.168.10.0/24
    |                         Gateway: 192.168.10.1
    |
    +-- VLAN 20: Wi-Fi       192.168.20.0/24
    |                         Gateway: 192.168.20.1
    |
    +-- VLAN 30: Servers     192.168.30.0/24
    |                         Gateway: 192.168.30.1
    |
    +-- VLAN 40: Printers    192.168.40.0/24
                              Gateway: 192.168.40.1
```

> Upar diye gaye IP addresses example hain. Actual network ke IP addresses unki jagah likhein.

## 5. Manual Drawing Steps

1. Paper, whiteboard, draw.io ya Visio open karein.
2. Sabse upar Internet/ISP ka symbol banayein.
3. ISP ke neeche firewall ya router place karein.
4. Firewall se core switch ka connection line banayein.
5. Core switch ke neeche access switches place karein.
6. Access switches se PCs, servers, printers aur APs connect karein.
7. Har line par dono devices ke interface names likhein.
8. Har device ke neeche hostname aur management IP likhein.
9. VLANs ko alag colors se mark karein.
10. Primary link ko solid line aur backup link ko dotted line se show karein.

## 6. Link Documentation Format

| Source Device | Source Port | Destination Device | Destination Port | Link Type | VLANs |
|---|---|---|---|---|---|
| FW-01 | LAN-G0/1 | CS-01 | G0/1 | Trunk | 10,20,30,40,99 |
| CS-01 | G0/2 | AS-01 | G0/1 | Trunk | 10,20,99 |
| CS-01 | G0/3 | AS-02 | G0/1 | Trunk | 30,40,99 |
| AS-01 | F0/1 | PC-01 | NIC | Access | 10 |
| AS-02 | F0/1 | Server-01 | NIC | Access | 30 |

## 7. Recommended Symbols and Colors

| Item | Suggested Color/Style |
|---|---|
| Router/Firewall | Red |
| Core switch | Blue |
| Access switch | Light blue |
| Server | Green |
| User device | Grey |
| Wi-Fi/AP | Orange |
| Primary link | Solid line |
| Backup link | Dotted line |

## 8. Final Verification Checklist

- [ ] Kya har device ka naam clearly visible hai?
- [ ] Kya har link ke dono interface names likhe hain?
- [ ] Kya management IP addresses add kiye gaye hain?
- [ ] Kya VLAN, subnet aur gateway details correct hain?
- [ ] Kya trunk aur access links identify kiye gaye hain?
- [ ] Kya backup links aur single points of failure mark kiye gaye hain?
- [ ] Kya topology physical aur logical dono views mein complete hai?
- [ ] Kya document ki date aur version add ki gayi hai?

## 9. Document Details

| Field | Value |
|---|---|
| Document Name | Manual Network Topology |
| Version | 1.0 |
| Prepared By | __________________ |
| Date | __________________ |
| Reviewed By | __________________ |

