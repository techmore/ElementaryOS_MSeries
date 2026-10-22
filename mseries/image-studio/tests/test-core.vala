void test_parse_mem_available () {
    var bytes = HostCapabilities.parse_mem_available ("MemTotal:       32000000 kB\nMemAvailable:    6400000 kB\n");
    assert (bytes == 6400000UL * 1024UL);
}

void test_parse_missing_mem_available () {
    assert (HostCapabilities.parse_mem_available ("MemTotal: 1000 kB\n") == 0);
    assert (HostCapabilities.parse_mem_available ("MemAvailable: unknown kB\n") == 0);
}

void test_generation_gate () {
    var reserve = GenerationGate.DESKTOP_RESERVE_BYTES;
    assert (!GenerationGate.can_run (false, reserve + 8UL * 1024UL * 1024UL * 1024UL, 2UL * 1024UL * 1024UL * 1024UL));
    assert (!GenerationGate.can_run (true, reserve + 1UL, 2UL));
    assert (!GenerationGate.can_run (true, reserve + 2UL * 1024UL * 1024UL * 1024UL, 0));
    assert (GenerationGate.can_run (true, reserve + 3UL * 1024UL * 1024UL * 1024UL, 2UL * 1024UL * 1024UL * 1024UL));
}

void test_recipe_round_trip () {
    try {
        var recipe = new GenerationRecipe ();
        recipe.prompt = "Adult streamer portrait, warm light, café study room";
        recipe.intent = "Streamer scene";
        recipe.workflow = "Prompt type study";
        recipe.model_id = "test-model";
        recipe.lora_id = "test-lora";
        recipe.lora_weight = 0.8;
        recipe.batch_size = 3;
        recipe.tags = { "portrait", "streamer" };

        var parser = new Json.Parser ();
        parser.load_from_data (recipe.to_json ());
        var object = parser.get_root ().get_object ();
        assert (object.get_string_member ("prompt") == recipe.prompt);
        assert (object.get_string_member ("intent") == "Streamer scene");
        assert (object.get_string_member ("workflow") == "Prompt type study");
        assert (object.get_string_member ("model_id") == "test-model");
        assert (object.get_string_member ("lora_id") == "test-lora");
        assert (object.get_int_member ("batch_size") == 3);
        assert (object.get_array_member ("tags").get_length () == 2);
        assert (object.get_int_member ("schema_version") == 1);
    } catch (Error e) {
        assert_not_reached ();
    }
}

void test_recipe_store () {
    try {
        var temporary = DirUtils.make_tmp ("mseries-image-studio-XXXXXX");
        var recipe = new GenerationRecipe ();
        recipe.prompt = "Test recipe";
        recipe.workflow = "Model readiness";
        recipe.model_id = "test-model";
        recipe.tags = { "portrait", "streamer" };
        var path = RecipeStore.save (recipe, temporary);
        assert (FileUtils.test (path, FileTest.EXISTS));
        var loaded = RecipeStore.load_recent (10, temporary);
        assert (loaded.length == 1);
        assert (loaded[0].prompt == "Test recipe");
        assert (loaded[0].workflow == "Model readiness");
        assert (loaded[0].model_id == "test-model");
        assert (loaded[0].tags.length == 2);
        FileUtils.remove (path);
        DirUtils.remove (temporary);
    } catch (Error e) {
        assert_not_reached ();
    }
}

void test_output_store () {
    try {
        var temporary = DirUtils.make_tmp ("mseries-image-output-XXXXXX");
        uint8[] sample_png = { 0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a, 0x01, 0x02, 0x03 };
        var recipe = new GenerationRecipe ();
        recipe.prompt = "Alexandra Daddario as an adult college-age streamer";
        recipe.intent = "Streamer scene";
        recipe.model_id = "sample-model";
        recipe.lora_id = "sample-lora";
        recipe.tags = { "test", "adult" };

        var image_path = GenerationOutputStore.save_png (sample_png, recipe, temporary);
        var metadata_path = image_path.substring (0, image_path.length - 4) + ".json";
        assert (FileUtils.test (image_path, FileTest.EXISTS));
        assert (FileUtils.test (metadata_path, FileTest.EXISTS));
        assert (recipe.image_path == image_path);
        string metadata;
        FileUtils.get_contents (metadata_path, out metadata);
        var parser = new Json.Parser ();
        parser.load_from_data (metadata);
        var object = parser.get_root ().get_object ();
        assert (object.get_string_member ("prompt") == recipe.prompt);
        assert (object.get_string_member ("model_id") == "sample-model");
        assert (object.get_string_member ("lora_id") == "sample-lora");
        assert (object.get_string_member ("image_path") == image_path);
        assert (object.get_array_member ("tags").get_length () == 2);
        var outputs = GenerationOutputStore.load_recent (10, temporary);
        assert (outputs.length == 1);
        assert (outputs[0].image_path == image_path);
        assert (outputs[0].prompt == recipe.prompt);
        FileUtils.remove (image_path);
        FileUtils.remove (metadata_path);
        DirUtils.remove (temporary);
    } catch (Error e) {
        assert_not_reached ();
    }
}

void test_output_store_rejects_non_png () {
    try {
        var temporary = DirUtils.make_tmp ("mseries-image-output-invalid-XXXXXX");
        uint8[] bytes = { 0x01, 0x02, 0x03 };
        var recipe = new GenerationRecipe ();
        bool rejected = false;
        try {
            GenerationOutputStore.save_png (bytes, recipe, temporary);
        } catch (Error e) {
            rejected = true;
        }
        assert (rejected);
        DirUtils.remove (temporary);
    } catch (Error e) {
        assert_not_reached ();
    }
}

int main (string[] args) {
    Test.init (ref args);
    Test.add_func ("/host/memavailable", test_parse_mem_available);
    Test.add_func ("/host/memavailable-missing", test_parse_missing_mem_available);
    Test.add_func ("/generation/guard", test_generation_gate);
    Test.add_func ("/recipe/json", test_recipe_round_trip);
    Test.add_func ("/recipe/store", test_recipe_store);
    Test.add_func ("/output/store", test_output_store);
    Test.add_func ("/output/rejects-non-png", test_output_store_rejects_non_png);
    return Test.run ();
}
