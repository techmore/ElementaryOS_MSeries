public class GenerationOutputStore : Object {
    private const uint8[] PNG_SIGNATURE = { 0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a };

    public static string default_directory () {
        return Path.build_filename (Environment.get_user_data_dir (), "mseries-image-studio", "images");
    }

    public static string save_png (uint8[] png, GenerationRecipe recipe, string? directory = null) throws Error {
        if (!has_png_signature (png)) throw new IOError.INVALID_DATA ("The image engine did not return a PNG image.");

        var target_dir = directory ?? default_directory ();
        if (DirUtils.create_with_parents (target_dir, 0700) != 0 && !FileUtils.test (target_dir, FileTest.IS_DIR)) {
            throw new IOError.FAILED ("Could not create the image library.");
        }

        var stamp = new DateTime.now_local ().format ("%Y%m%d-%H%M%S");
        var name = "image-%s-%s".printf (stamp, Uuid.string_random ());
        var image_path = Path.build_filename (target_dir, name + ".png");
        var metadata_path = Path.build_filename (target_dir, name + ".json");
        var previous_image_path = recipe.image_path;
        recipe.image_path = image_path;
        try {
            string? etag;
            File.new_for_path (image_path).replace_contents (png, null, false, FileCreateFlags.PRIVATE, out etag);
            FileUtils.set_contents (metadata_path, recipe.to_json ());
        } catch (Error e) {
            recipe.image_path = previous_image_path;
            FileUtils.remove (image_path);
            FileUtils.remove (metadata_path);
            throw e;
        }
        return image_path;
    }

    public static GenerationRecipe[] load_recent (int limit = 100, string? directory = null) throws Error {
        var source_dir = directory ?? default_directory ();
        if (!FileUtils.test (source_dir, FileTest.IS_DIR)) return {};

        string[] filenames = {};
        var dir = Dir.open (source_dir);
        string? name;
        while ((name = dir.read_name ()) != null) {
            if (name.has_suffix (".json")) filenames += name;
        }
        for (int i = 0; i < filenames.length; i++) {
            for (int j = i + 1; j < filenames.length; j++) {
                if (filenames[i].collate (filenames[j]) < 0) {
                    var newer = filenames[i];
                    filenames[i] = filenames[j];
                    filenames[j] = newer;
                }
            }
        }

        GenerationRecipe[] outputs = {};
        for (int i = 0; i < filenames.length && outputs.length < limit; i++) {
            var metadata_path = Path.build_filename (source_dir, filenames[i]);
            try {
                string contents;
                FileUtils.get_contents (metadata_path, out contents);
                var recipe = GenerationRecipe.from_json (contents);
                var image_name = filenames[i].substring (0, filenames[i].length - 5) + ".png";
                var image_path = Path.build_filename (source_dir, image_name);
                if (FileUtils.test (image_path, FileTest.EXISTS)) {
                    recipe.image_path = image_path;
                    outputs += recipe;
                }
            } catch (Error e) {
                warning ("Skipping unreadable image metadata %s: %s", metadata_path, e.message);
            }
        }
        return outputs;
    }

    private static bool has_png_signature (uint8[] bytes) {
        if (bytes.length < 8) return false;
        for (int i = 0; i < 8; i++) {
            if (bytes[i] != PNG_SIGNATURE[i]) return false;
        }
        return true;
    }
}
