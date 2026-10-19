import json, os, sys, tempfile, unittest
sys.path.insert(0, os.path.dirname(__file__))
import airplay_core as c


def node(i, name, desc, media="Audio/Sink", state="suspended"):
    return {"id": i, "type": "PipeWire:Interface:Node",
            "info": {"state": state, "props": {"node.name": name, "node.description": desc, "media.class": media}}}


DUMP = [
    node(56, "raop_sink.Sonos-347E5C3E44AA.local.192.168.222.248.7000", "Barn_1st"),
    node(62, "raop_sink.zTV-Living-Room.local.192.168.222.245.7000", "zTV-Living Room"),
    node(64, "raop_sink.Eve1.local.192.168.222.8.7000", "bedroom"),
    node(81, "alsa_output.speakers", "Speakers"),
    node(90, "raop_sink.Fake.local.1.2.3.4.7000", "not a sink", media="Audio/Source"),
]


class Core(unittest.TestCase):
    def test_destinations_sorted_and_filtered(self):
        d = c.destinations(DUMP)
        self.assertEqual([x["name"] for x in d], ["Barn_1st", "bedroom", "zTV-Living Room"])
        self.assertEqual(d[0]["key"], "Sonos-347E5C3E44AA")
        self.assertEqual(d[2]["key"], "zTV-Living-Room")

    def test_toggle(self):
        self.assertEqual(c.toggle([], "a"), ["a"])
        self.assertEqual(c.toggle(["a", "b"], "a"), ["b"])

    def test_args_contain_each_member_once(self):
        a = c.module_args(["Eve1", "Eve1", "zTV-Living-Room"])
        self.assertEqual(a.count("create-stream"), 2)
        self.assertIn(c.GROUP_NODE_NAME, a)
        self.assertIn("raop_sink\\\\.Eve1\\\\.local", a)

    def test_client_conf(self):
        conf = c.client_conf(["Eve1"])
        self.assertIn("libpipewire-module-combine-stream", conf)
        self.assertIn("libpipewire-module-protocol-native", conf)
        self.assertIn(c.GROUP_NODE_NAME, conf)

    def test_group_sink_and_members(self):
        dump = DUMP + [
            node(201, c.GROUP_NODE_NAME, "AirPlay Group"),
            node(202, "output." + c.GROUP_NODE_NAME + ".1", "x", media="Stream/Output/Audio"),
            {"id": 203, "type": "PipeWire:Interface:Link", "info": {"output-node-id": 202, "input-node-id": 64}},
            {"id": 204, "type": "PipeWire:Interface:Link", "info": {"output-node-id": 999, "input-node-id": 56}},
        ]
        self.assertEqual(c.group_sink(dump), 201)
        self.assertEqual(c.group_members(dump), {"Eve1"})
        self.assertEqual(c.group_members(DUMP), set())

    def test_state_roundtrip_and_corrupt(self):
        with tempfile.TemporaryDirectory() as t:
            p = os.path.join(t, "x", "airplay.json")
            self.assertEqual(c.load_state(p), [])
            c.save_state(["b", "a", "a"], p)
            self.assertEqual(c.load_state(p), ["a", "b"])
            with open(p, "w") as f:
                f.write("{bad")
            self.assertEqual(c.load_state(p), [])


if __name__ == "__main__":
    unittest.main()
