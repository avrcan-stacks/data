# 89 — Spajanje md3 (/home) u md2 (/) — runbook

Server: `65.108.196.92` (Hetzner HEL1-DC1, Server Auction #2920421). BIOS boot, GPT, 2× NVMe 3,5 TB.
Cilj: ukloniti md3 (1,5 TiB, /home) i proširiti md2 (/) s 2 TiB na ~3,5 TiB. Downtime je dopušten.

## 1. Stanje i pripremljeno

| Stavka | Stanje |
|---|---|
| GPT oba diska | p3 `10489856–4234153983` (2 TiB), p4 `4234153984–7501476494` (1,5 TiB), p5 BIOS boot `2048–4095` (ne dirati) |
| md2 | RAID1, metadata 1.2, internal bitmap, ext4 na `/` (80 % zauzeto, 389 G slobodno) |
| md3 | RAID1 na p4, bio `/home`; sadržaj samo Immich backupi (6,7 GB) |
| `/home` kopija | `/opt/stacks/data/backups/md3-merge/home-copy/` (checksumi OK) |
| GPT backupi | `/opt/stacks/data/backups/md3-merge/gpt-nvme*.bin` + Borg arhiv `md3-merge-gpt-<ts>` u `ssh://storagebox/./backups/postgres/repository` (`borg check` rc=0) |
| fstab | redak `/home` uklonjen (original: `backups/md3-merge/fstab.orig`) |
| Kontejneri | svi (117) zaustavljeni; popis u `backups/md3-merge/running-containers.txt`; baze zaustavljene čisto |
| Borg offsite | postoji **samo za baze**; za ostale podatke (Immich, volumeni) nema offsite kopije — rizik prihvaćen |
| Skripta | `scripts/merge-md3-into-md2.sh` (faze `prep`, `free` izvršene; `repart`/`grow` se rade ručno u Rescueu) |

Napomena: prvi pokušaj (softverski `reboot`) nije ušao u Rescue, server se podigao u normalni Ubuntu. Za Rescue treba **automatski hardverski reset** iz Robota. Nakon tog boota kernel je ponovno sastavio md3 (nije montiran); u Rescueu ga zaustavljamo.

## 2. Korak 0 — na normalnom serveru

```bash
# na SVOM računalu: kopija GPT backupa
scp -r root@65.108.196.92:/opt/stacks/data/backups/md3-merge/gpt-* .

# na serveru: zaustavi sve što se možda podiglo
docker ps -q | xargs -r -P 16 -n 5 docker stop -t 120
docker ps          # mora biti prazno
sync
```

## 3. Korak 1 — Rescue

Robot → tab **Rescue** → Linux (Debian Trixie) → javni ključ → **Activate rescue system** (vrijedi 60 min).
Tab **Reset** → **Execute an automatic hardware reset**. Pričekaj 1–2 min.

```bash
ssh-keygen -R 65.108.196.92
ssh root@65.108.196.92
uname -r        # NE smije biti 5.15...; prompt kaže "rescue"
```

## 4. Korak 2 — pregled (samo čitanje)

```bash
apt update && apt install -y mdadm gdisk
cat /proc/mdstat
lsblk
sgdisk -p /dev/nvme0n1
sgdisk -p /dev/nvme1n1
```
**STOP** ako oba diska nemaju točno:
```
3   10489856    4234153983   2.0 TiB     FD00
4   4234153984  7501476494   1.5 TiB     FD00
5   2048        4095         1024.0 KiB  EF02
```

## 5. Korak 3 — backup GPT-a i zaustavljanje polja

```bash
sgdisk --backup=/root/gpt-nvme0n1.bin /dev/nvme0n1
sgdisk --backup=/root/gpt-nvme1n1.bin /dev/nvme1n1
mdadm --stop --scan
cat /proc/mdstat     # ne smije biti nijedan mdN
```

## 6. Korak 4 — promjena particija (prvo prvi disk, provjera, pa drugi)

```bash
d=/dev/nvme0n1
G=$(sgdisk -i 3 $d | awk '/Partition unique GUID/{print $4}'); echo "GUID=$G"
sgdisk -d 4 -d 3 $d
sgdisk -n 3:10489856:0 -t 3:FD00 -u 3:$G $d
sgdisk -p $d
```
**STOP** ako p3 nema Start **10489856** i End **7501476494**, ili p4 postoji. Povrat: `sgdisk --load-backup=/root/gpt-nvme0n1.bin $d`.

Ako je točno, drugi disk:

```bash
d=/dev/nvme1n1
G=$(sgdisk -i 3 $d | awk '/Partition unique GUID/{print $4}'); echo "GUID=$G"
sgdisk -d 4 -d 3 $d
sgdisk -n 3:10489856:0 -t 3:FD00 -u 3:$G $d
sgdisk -p $d
partprobe /dev/nvme0n1 /dev/nvme1n1
lsblk
```

## 7. Korak 5 — sastavljanje i proširenje md2

```bash
mdadm --assemble /dev/md2 /dev/nvme0n1p3 /dev/nvme1n1p3
cat /proc/mdstat                  # [UU], ~2T
mdadm --grow /dev/md2 --size=max
cat /proc/mdstat                  # resync nove regije
```
Ako `--grow` javi grešku zbog bitmape:
```bash
mdadm --grow /dev/md2 --bitmap=none
mdadm --grow /dev/md2 --size=max
mdadm --grow /dev/md2 --bitmap=internal
```

## 8. Korak 6 — datotečni sustav

```bash
e2fsck -f /dev/md2        # mora završiti bez grešaka
resize2fs /dev/md2
e2fsck -fn /dev/md2       # završna provjera
```
Resync polja može teći paralelno.

## 9. Korak 7 — konfiguracija (chroot)

```bash
mount /dev/md2 /mnt
mount /dev/md1 /mnt/boot
mount --bind /dev /mnt/dev; mount --bind /proc /mnt/proc; mount --bind /sys /mnt/sys
chroot /mnt /bin/bash
```
Unutar chroota:
```bash
sed -i '\#/dev/md/3#d' /etc/mdadm/mdadm.conf
grep -v '^#' /etc/mdadm/mdadm.conf       # mora ostati md/0, md/1, md/2
grep -c ' /home ' /etc/fstab             # mora biti 0
update-initramfs -u -k all
exit
```
```bash
umount /mnt/sys /mnt/proc /mnt/dev /mnt/boot /mnt
cat /proc/mdstat
reboot
```
GRUB se ne mijenja (`/boot` = md1 i BIOS boot p5 netaknuti).

## 10. Korak 8 — provjera nakon boota

```bash
ssh-keygen -R 65.108.196.92; ssh root@65.108.196.92
df -h /            # ~3,5T
cat /proc/mdstat   # md0, md1, md2 [UU]; md2 možda još resynca
lsblk
docker ps | wc -l
```
Ako se kontejneri nisu sami podigli (prvo baze):
```bash
docker start postgis postgres immich-db fiskal_domibus_mysql racunai_domibus_mysql
sleep 20
docker start $(grep -vxE 'postgis|postgres|immich-db|fiskal_domibus_mysql|racunai_domibus_mysql' /opt/stacks/data/backups/md3-merge/running-containers.txt)
docker exec postgis pg_isready
```

## 11. Povrat (rollback)

- Prije proširenja polja: `sgdisk --load-backup=/root/gpt-nvme0n1.bin /dev/nvme0n1` (isto za nvme1n1), `partprobe`. Vraća p3 + p4.
- Ako je `/root` u rescueu prazan: backupi su na tvom računalu (korak 0) i u Borgu (`borg extract` arhiva `md3-merge-gpt-*`, passphrase iz `/root/.config/borg-postgres/passphrase`).
- Bitno: `sgdisk` mijenja samo tablicu; podaci se ne diraju sve dok početni sektor p3 ostaje 10489856.

## 12. Završno (nakon uspjeha)

- Po želji obrisati `backups/md3-merge/home-copy/` kad je `/home` sadržaj potvrđen/premješten na željeno mjesto.
- Opcionalno: Borg backup ostalih podataka (Immich, volumeni) — danas ne postoji.
- Zapisati rezultat (`df -h /`, `mdadm --detail /dev/md2`) u ovaj dokument.

## 13. Rezultat (izvedeno 2026-11-19)

| Provjera | Rezultat |
|---|---|
| `df -h /` | `/dev/md2` 3,5T, zauzeto 1,5T (45 %), slobodno 1,9T (prije 389G) |
| GPT (oba diska) | p3 `10489856–7501476494` (3,5 TiB), p4 ne postoji, p1/p2/p5 netaknuti |
| `/proc/mdstat` | `md0`, `md1`, `md2` `[UU]`; resync nove regije završen; `md3` ne postoji |
| `mdadm.conf` / fstab | samo `md/0`, `md/1`, `md/2`; nema `/home` retka |
| Boot | normalan (kernel 5.15.0-203), ext4 bez grešaka |
| Kontejneri | svi pokrenuti, nijedan `unhealthy`; `postgis` accepting connections |

Napomene:
- `sofascore-proxy-bridge` (`alpine/socat`, zaustavljen, bez volumena) uklonjen je na zahtjev, zajedno s imageom.
- Sadržaj bivšeg `/home` (Immich backupi iz cutovera, ~6,7 GB) obrisan je na zahtjev jer je cutover uspješno završen.
- Backupi GPT-a, fstab-a, mdadm.conf-a i logovi ostaju u `backups/md3-merge/` (gitignored) i u Borg arhivu `md3-merge-gpt-<ts>`.
- Offsite Borg i dalje pokriva samo baze (Immich i volumeni nemaju offsite kopiju).
