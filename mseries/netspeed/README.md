# Network indicator enhancements

This restores the network indicator work from the sibling
`mseries-usage-troubleshooter-docked-lid` branch while preserving this branch's
existing speed-in-panel feature.

The built panel module adds:

- A Wi-Fi list that shows the connected network by default. Use the chevron to
  reveal other networks; when disconnected, the full list remains visible.
- A collapsible **Network Usage** section with **Apps**, **Hosts**, and **DNS**
  views and Today, 7-day, and 30-day ranges.
- Host labels learned from `systemd-resolved`'s query monitor and cache. It
  doesn't issue reverse-DNS lookups.

The original full upstream diff is preserved in `panel-network.patch` at the
commit recorded in `PINNED_SHA`. The build applies its Wi-Fi, usage-widget, and
stylesheet sections on top of this branch's speed patches, then uses
`network-usage-wiring.patch` to add the widget to the menu. This keeps the
separate optional speed readout in the panel.

Build and install the panel module with:

```sh
bash mseries/install-network-throughput.sh
```

To populate Apps, Hosts, and DNS views, install the local user logger:

```sh
bash mseries/netspeed/netusage/install.sh
```

The logger writes to `~/.local/share/netusage/usage.db`; it does not upload
data. Per-app byte totals use TCP socket counters, so QUIC/HTTP3 is not
attributed to apps. DNS names and lookup counts come from
`resolvectl monitor --json=short`; the speed graph remains the total-traffic
view. Disable the logger with:

```sh
systemctl --user disable --now netusage.service
```
