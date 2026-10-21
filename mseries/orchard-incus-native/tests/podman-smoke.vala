private async void exercise () throws Error {
    // Parsing: real-world shapes, including null Names/Ports and a multi-port range.
    var containers = PodmanClient.parse_containers ("""[
      {"Id":"aaaaaaaaaaaaaaaa","Names":["web"],"Image":"docker.io/library/nginx:1","State":"running","Status":"Up 2 hours","Created":10,
       "Ports":[{"host_ip":"127.0.0.1","host_port":8080,"container_port":80,"range":1,"protocol":"tcp"}]},
      {"Id":"bbbbbbbbbbbbbbbb","Names":["db"],"Image":"postgres","State":"exited","Status":"Exited (0) 1 hour ago","Ports":null,"PodName":"stack"},
      {"Id":"cccccccccccccccccccc","Names":null,"Image":"alpine","State":"running","Status":"Up 1 minute",
       "Ports":[{"host_ip":"","host_port":9000,"container_port":9000,"range":3,"protocol":"udp"}]}
    ]""");
    assert (containers.length == 3);
    assert (containers[0].name == "web" && containers[0].running && containers[0].ports == "127.0.0.1:8080→80/tcp");
    assert (containers[1].name == "db" && !containers[1].running && containers[1].ports == "" && containers[1].pod == "stack");
    assert (containers[2].name == "cccccccccccc" && containers[2].ports == "9000-9002→9000-9002/udp");
    var ordered = PodmanClient.sorted_containers (containers);
    assert (ordered[0].name == "cccccccccccc" && ordered[1].name == "web" && ordered[2].name == "db");

    var images = PodmanClient.parse_images ("""[{"Id":"1111111111111111","Names":["localhost/app:1"],"Size":2048,"Containers":2},{"Id":"2222222222222222222","Names":null,"Size":5}]""");
    assert (images.length == 2 && images[0].name == "localhost/app:1" && images[0].size == 2048 && images[0].containers == 2);
    assert (images[1].name == "<untagged> 222222222222");
    var volumes = PodmanClient.parse_volumes ("""[{"Name":"data","Driver":"local","Mountpoint":"/v/data/_data"}]""");
    assert (volumes.length == 1 && volumes[0].name == "data" && volumes[0].driver == "local");
    assert (PodmanClient.parse_containers ("null").length == 0 && PodmanClient.parse_images ("").length == 0);
    bool bad = false;
    try { PodmanClient.parse_volumes ("{}"); } catch (Error e) { bad = true; }
    assert (bad);

    // Subprocess path against the fixture binary named by $ORCHARD_PODMAN.
    var client = new PodmanClient (2);
    assert (client.installed ());
    assert ((yield client.list_containers ()).length == 3);
    assert ((yield client.list_images ()).length == 2);
    assert ((yield client.list_volumes ()).length == 1);
    yield client.container_action ("web", "restart");
    yield client.remove_container ("db");
    yield client.remove_image ("1111");
    yield client.remove_volume ("data");

    bool refused = false;
    try { yield client.container_action ("web", "kill"); } catch (Error e) { refused = e is IOError.INVALID_ARGUMENT; }
    assert (refused);

    string failure = "";
    try { yield client.remove_volume ("busy"); } catch (Error e) { failure = e.message; }
    assert (failure == "volume busy is in use by a container");

    bool timed_out = false;
    try { yield client.run ({ "hang" }); } catch (Error e) { timed_out = e is IOError.TIMED_OUT; }
    assert (timed_out);

    Environment.set_variable ("ORCHARD_PODMAN", "/nonexistent/podman", true);
    var missing = new PodmanClient ();
    assert (!missing.installed ());
    bool unavailable = false;
    try { yield missing.list_containers (); } catch (Error e) { unavailable = e is IOError.NOT_FOUND; }
    assert (unavailable);
    print ("Podman parsing, ordering, actions, refusal, failure, timeout and missing-binary checks passed.\n");
}
int main () {
    var loop = new MainLoop ();
    int result = 1;
    exercise.begin ((obj, res) => {
        try { exercise.end (res); result = 0; }
        catch (Error e) { stderr.printf ("%s\n", e.message); }
        loop.quit ();
    });
    loop.run ();
    return result;
}
