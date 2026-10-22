public class GenerationRecipe : Object {
    public string prompt { get; set; default = ""; }
    public string negative_prompt { get; set; default = ""; }
    public string intent { get; set; default = "Portrait"; }
    public string workflow { get; set; default = "Freeform"; }
    public string model_id { get; set; default = ""; }
    public string lora_id { get; set; default = ""; }
    public double lora_weight { get; set; default = 1.0; }
    public int width { get; set; default = 512; }
    public int height { get; set; default = 512; }
    public int batch_size { get; set; default = 1; }
    public int seed { get; set; default = -1; }
    public string[] tags { get; set; default = {}; }
    public string engine_id { get; set; default = "unconfigured"; }
    public string image_path { get; set; default = ""; }
    public string app_version { get; set; default = "0.1.0"; }

    public string to_json () {
        var builder = new Json.Builder ();
        builder.begin_object ()
            .set_member_name ("schema_version").add_int_value (1)
            .set_member_name ("created_at").add_string_value (new DateTime.now_local ().format_iso8601 ())
            .set_member_name ("prompt").add_string_value (prompt)
            .set_member_name ("negative_prompt").add_string_value (negative_prompt)
            .set_member_name ("intent").add_string_value (intent)
            .set_member_name ("workflow").add_string_value (workflow)
            .set_member_name ("model_id").add_string_value (model_id)
            .set_member_name ("lora_id").add_string_value (lora_id)
            .set_member_name ("lora_weight").add_double_value (lora_weight)
            .set_member_name ("width").add_int_value (width)
            .set_member_name ("height").add_int_value (height)
            .set_member_name ("batch_size").add_int_value (batch_size)
            .set_member_name ("seed").add_int_value (seed)
            .set_member_name ("engine_id").add_string_value (engine_id)
            .set_member_name ("image_path").add_string_value (image_path)
            .set_member_name ("app_version").add_string_value (app_version)
            .set_member_name ("tags").begin_array ();
        foreach (var tag in tags) builder.add_string_value (tag);
        builder.end_array ().end_object ();

        var generator = new Json.Generator ();
        generator.set_root (builder.get_root ());
        generator.pretty = true;
        return generator.to_data (null);
    }

    public static GenerationRecipe from_json (string contents) throws Error {
        var parser = new Json.Parser ();
        parser.load_from_data (contents);
        var root = parser.get_root ();
        if (root == null || root.get_node_type () != Json.NodeType.OBJECT) {
            throw new IOError.INVALID_DATA ("Recipe is not a JSON object.");
        }
        var object = root.get_object ();
        var recipe = new GenerationRecipe ();
        if (object.has_member ("prompt")) recipe.prompt = object.get_string_member ("prompt");
        if (object.has_member ("negative_prompt")) recipe.negative_prompt = object.get_string_member ("negative_prompt");
        if (object.has_member ("intent")) recipe.intent = object.get_string_member ("intent");
        if (object.has_member ("workflow")) recipe.workflow = object.get_string_member ("workflow");
        if (object.has_member ("model_id")) recipe.model_id = object.get_string_member ("model_id");
        if (object.has_member ("lora_id")) recipe.lora_id = object.get_string_member ("lora_id");
        if (object.has_member ("lora_weight")) recipe.lora_weight = object.get_double_member ("lora_weight");
        if (object.has_member ("width")) recipe.width = (int) object.get_int_member ("width");
        if (object.has_member ("height")) recipe.height = (int) object.get_int_member ("height");
        if (object.has_member ("batch_size")) recipe.batch_size = (int) object.get_int_member ("batch_size");
        if (object.has_member ("seed")) recipe.seed = (int) object.get_int_member ("seed");
        if (object.has_member ("engine_id")) recipe.engine_id = object.get_string_member ("engine_id");
        if (object.has_member ("image_path")) recipe.image_path = object.get_string_member ("image_path");
        if (object.has_member ("app_version")) recipe.app_version = object.get_string_member ("app_version");
        if (object.has_member ("tags") && object.get_member ("tags").get_node_type () == Json.NodeType.ARRAY) {
            var array = object.get_array_member ("tags");
            string[] tags = {};
            for (uint i = 0; i < array.get_length (); i++) {
                var item = array.get_element (i);
                if (item.get_value_type () == typeof (string)) tags += item.get_string ();
            }
            recipe.tags = tags;
        }
        return recipe;
    }
}
