public class RecipeStore : Object {
    public static string default_directory () {
        return Path.build_filename (Environment.get_user_data_dir (), "mseries-image-studio", "recipes");
    }

    public static string save (GenerationRecipe recipe, string? directory = null) throws Error {
        var target_dir = directory ?? default_directory ();
        if (DirUtils.create_with_parents (target_dir, 0700) != 0 && !FileUtils.test (target_dir, FileTest.IS_DIR)) {
            throw new IOError.FAILED ("Could not create the recipe library.");
        }
        var stamp = new DateTime.now_local ().format ("%Y%m%d-%H%M%S");
        var path = Path.build_filename (target_dir, "recipe-%s-%s.json".printf (stamp, Uuid.string_random ()));
        FileUtils.set_contents (path, recipe.to_json ());
        return path;
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

        GenerationRecipe[] recipes = {};
        for (int i = 0; i < filenames.length && recipes.length < limit; i++) {
            var path = Path.build_filename (source_dir, filenames[i]);
            try {
                string contents;
                FileUtils.get_contents (path, out contents);
                recipes += GenerationRecipe.from_json (contents);
            } catch (Error e) {
                warning ("Skipping unreadable image recipe %s: %s", path, e.message);
            }
        }
        return recipes;
    }
}
