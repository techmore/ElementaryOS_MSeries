//! Native review and sequential comparison workspaces.
use crate::{Recipe, recipe::load_outputs};
use gtk::prelude::*;
use std::{cell::RefCell, path::Path, rc::Rc};

type Reuse = Rc<dyn Fn(&Recipe)>;
type Snapshot = Rc<dyn Fn() -> Recipe>;

fn label(text: &str) -> gtk::Label {
    let label = gtk::Label::new(Some(text));
    label.set_xalign(0.0);
    label.set_wrap(true);
    label
}
fn page(title: &str) -> gtk::Box {
    let page = gtk::Box::new(gtk::Orientation::Vertical, 16);
    page.add_css_class("pantheon-inset");
    let title = label(title);
    title.add_css_class("title-2");
    page.append(&title);
    page
}
fn scroll(page: &gtk::Box) -> gtk::Widget {
    gtk::ScrolledWindow::builder()
        .child(page)
        .hscrollbar_policy(gtk::PolicyType::Never)
        .build()
        .upcast()
}
fn base() -> std::path::PathBuf {
    gtk::glib::user_data_dir().join("mseries-image-studio")
}
fn title(recipe: &Recipe) -> String {
    Path::new(&recipe.image_path)
        .file_stem()
        .map(|v| v.to_string_lossy().replace('-', " "))
        .unwrap_or_else(|| recipe.intent.clone())
}
fn text(view: &gtk::TextView) -> String {
    let buffer = view.buffer();
    buffer
        .text(&buffer.start_iter(), &buffer.end_iter(), true)
        .to_string()
}
fn run(script: &'static str, arguments: Vec<String>, status: &gtk::Label, button: &gtk::Button) {
    let directory = base();
    if directory.join("generation.lock").exists() || directory.join("batch.lock").exists() {
        status.set_text("A workflow is active. Stop it or wait before starting another.");
        return;
    }
    let _ = std::fs::remove_file(directory.join("cancel.request"));
    button.set_sensitive(false);
    status.set_text("Starting local workflow…");
    let (tx, rx) = std::sync::mpsc::channel();
    std::thread::spawn(move || {
        let result = std::process::Command::new("python3")
            .arg("-c")
            .arg(script)
            .args(arguments)
            .output();
        let message = match result {
            Ok(output) if output.status.success() => {
                "Workflow finished. Results are saved locally.".to_string()
            }
            Ok(output) => format!(
                "Workflow unavailable: {}",
                String::from_utf8_lossy(&output.stderr)
                    .chars()
                    .take(3000)
                    .collect::<String>()
            ),
            Err(error) => format!("Could not start workflow: {error}"),
        };
        let _ = tx.send(message);
    });
    let status = status.clone();
    let button = button.clone();
    gtk::glib::timeout_add_seconds_local(1, move || match rx.try_recv() {
        Ok(message) => {
            status.set_text(&message);
            button.set_sensitive(true);
            gtk::glib::ControlFlow::Break
        }
        Err(std::sync::mpsc::TryRecvError::Disconnected) => {
            status.set_text("Workflow worker disconnected.");
            button.set_sensitive(true);
            gtk::glib::ControlFlow::Break
        }
        Err(_) => gtk::glib::ControlFlow::Continue,
    });
}

fn review_text(value: &serde_json::Value, path: &str) -> String {
    let score = value["overall_score"]
        .as_f64()
        .map(|v| format!("{v:.2}/5 (advisory)"))
        .unwrap_or_else(|| "Not scored".into());
    let mut lines = vec![format!(
        "Review: {}\n{}\nOverall: {}\n\n{}\n",
        value["recipe_path"].as_str().unwrap_or("Image unavailable"),
        value["evaluator"]
            .as_str()
            .unwrap_or("Evaluator unavailable"),
        score,
        value["summary"].as_str().unwrap_or("No summary")
    )];
    if let Some(scores) = value["scores"].as_object() {
        for (name, row) in scores {
            lines.push(format!(
                "{}: {} / 5\n{}\n",
                name.replace('_', " "),
                row["score"],
                row["reason"].as_str().unwrap_or("No explanation")
            ));
        }
    }
    lines.push(format!(
        "Suggested prompt\n{}\n\nRubric: {}\nReport retained at {}",
        value["suggested_prompt"].as_str().unwrap_or("Unavailable"),
        value["rubric"].as_str().unwrap_or("Unavailable"),
        path
    ));
    lines.join("\n")
}

pub fn review(on_reuse: Reuse) -> gtk::Widget {
    let page = page("Review an image");
    page.append(&label("Compare a generated image with your goal and an optional reference. Qwen vision runs locally after generation unloads. Scores are advisory; each report records its evaluator, rubric, image digest and settings."));
    let images = Rc::new(RefCell::new(Vec::<Recipe>::new()));
    let names = gtk::StringList::new(&[]);
    let selection = gtk::DropDown::new(Some(names.clone()), None::<gtk::Expression>);
    selection.update_property(&[gtk::accessible::Property::Label("Image to review")]);
    page.append(&selection);
    let reference_names = gtk::StringList::new(&["No reference"]);
    let reference = gtk::DropDown::new(Some(reference_names.clone()), None::<gtk::Expression>);
    reference.update_property(&[gtk::accessible::Property::Label("Optional reference image")]);
    page.append(&label("Optional appearance or composition reference"));
    page.append(&reference);
    let refresh = gtk::Button::with_label("Refresh image list");
    refresh.set_halign(gtk::Align::Start);
    page.append(&refresh);
    let picture = gtk::Picture::new();
    picture.set_can_shrink(true);
    picture.set_content_fit(gtk::ContentFit::Contain);
    picture.set_size_request(-1, 280);
    page.append(&picture);
    let source = label("Select an image from Library.");
    source.set_lines(3);
    source.set_ellipsize(gtk::pango::EllipsizeMode::End);
    page.append(&source);
    let refill = {
        let images = images.clone();
        let names = names.clone();
        let reference_names = reference_names.clone();
        let picture = picture.clone();
        let source = source.clone();
        move || {
            let values = load_outputs(&base().join("images"), 100).unwrap_or_default();
            names.splice(0, names.n_items(), &[]);
            reference_names.splice(0, reference_names.n_items(), &["No reference"]);
            for recipe in &values {
                names.append(&title(recipe));
                reference_names.append(&title(recipe));
            }
            if let Some(recipe) = values.first() {
                picture.set_filename(Some(&recipe.image_path));
                source.set_text(&recipe.prompt);
            } else {
                picture.set_filename(None::<&str>);
                source.set_text("No saved images yet.");
            }
            *images.borrow_mut() = values;
        }
    };
    refill();
    refresh.connect_clicked(move |_| refill());
    {
        let images = images.clone();
        let picture = picture.clone();
        let source = source.clone();
        selection.connect_selected_notify(move |selection| {
            if let Some(recipe) = images.borrow().get(selection.selected() as usize) {
                picture.set_filename(Some(&recipe.image_path));
                source.set_text(&recipe.prompt);
            }
        });
    }
    page.append(&label("What should the reviewer prioritize?"));
    let rubric = gtk::TextView::new();
    rubric.update_property(&[gtk::accessible::Property::Label(
        "Vision review goal and rubric",
    )]);
    rubric.set_wrap_mode(gtk::WrapMode::WordChar);
    rubric.set_size_request(-1, 90);
    rubric.buffer().set_text("Natural adult expression, accurate cozy knitwear, warm comfortable lighting, coherent composition and believable hands. Preserve the subject and intent.");
    page.append(&rubric);
    let review = gtk::Button::with_label("Review selected image");
    review.add_css_class("suggested-action");
    review.set_halign(gtk::Align::Start);
    page.append(&review);
    let status = label(
        "Requires Qwen3-VL 2B, its matching vision projector, and the local llama-server runtime.",
    );
    page.append(&status);
    let report = gtk::TextView::new();
    report.set_editable(false);
    report.set_wrap_mode(gtk::WrapMode::WordChar);
    report.set_size_request(-1, 220);
    page.append(&report);
    let suggestion = Rc::new(RefCell::new(String::new()));
    let report_recipe = Rc::new(RefCell::new(None::<Recipe>));
    let use_suggestion = gtk::Button::with_label("Use suggested prompt");
    use_suggestion.set_halign(gtk::Align::Start);
    use_suggestion.set_sensitive(false);
    page.append(&use_suggestion);
    {
        let images = images.clone();
        let report = report.clone();
        let suggestion = suggestion.clone();
        let report_recipe = report_recipe.clone();
        let use_suggestion = use_suggestion.clone();
        selection.connect_selected_notify(move |selection| {
            *suggestion.borrow_mut() = String::new();
            *report_recipe.borrow_mut() = None;
            use_suggestion.set_sensitive(false);
            report
                .buffer()
                .set_text("No saved review for this image yet.");
            if let Some(recipe) = images.borrow().get(selection.selected() as usize) {
                let path = Path::new(&recipe.image_path).with_extension("review.json");
                if let Ok(raw) = std::fs::read(&path) {
                    if let Ok(value) = serde_json::from_slice::<serde_json::Value>(&raw) {
                        report
                            .buffer()
                            .set_text(&review_text(&value, &path.to_string_lossy()));
                        *suggestion.borrow_mut() =
                            value["suggested_prompt"].as_str().unwrap_or("").to_string();
                        *report_recipe.borrow_mut() = Some(recipe.clone());
                        use_suggestion.set_sensitive(!suggestion.borrow().is_empty());
                    }
                }
            }
        });
    }
    {
        let images = images.clone();
        let selection = selection.clone();
        let reference = reference.clone();
        let rubric = rubric.clone();
        let status = status.clone();
        review.connect_clicked(move |button| {
            let values = images.borrow();
            let Some(recipe) = values.get(selection.selected() as usize) else {
                status.set_text("Select a saved image first.");
                return;
            };
            let reference_path = reference
                .selected()
                .checked_sub(1)
                .and_then(|index| values.get(index as usize))
                .map(|r| r.image_path.clone())
                .unwrap_or_default();
            run(
                include_str!("review_image.py"),
                vec![
                    base().to_string_lossy().into_owned(),
                    Path::new(&recipe.image_path)
                        .with_extension("json")
                        .to_string_lossy()
                        .into_owned(),
                    text(&rubric),
                    reference_path,
                ],
                &status,
                button,
            );
        });
    }
    {
        let suggestion = suggestion.clone();
        let report_recipe = report_recipe.clone();
        use_suggestion.connect_clicked(move |_| {
            if let Some(mut recipe) = report_recipe.borrow().clone() {
                recipe.prompt = suggestion.borrow().clone();
                on_reuse(&recipe);
            }
        });
    }
    let mut previous = String::new();
    let weak = page.downgrade();
    gtk::glib::timeout_add_seconds_local(1, move || {
        if weak.upgrade().is_none() {
            return gtk::glib::ControlFlow::Break;
        }
        if let Ok(raw) = std::fs::read_to_string(base().join("review-status.json")) {
            if raw != previous {
                if let Ok(job) = serde_json::from_str::<serde_json::Value>(&raw) {
                    status.set_text(
                        job["status"]
                            .as_str()
                            .unwrap_or("Review status unavailable"),
                    );
                    if let Some(path) = job["report_path"].as_str() {
                        if let Ok(raw) = std::fs::read_to_string(path) {
                            if let Ok(value) = serde_json::from_str::<serde_json::Value>(&raw) {
                                report.buffer().set_text(&review_text(&value, path));
                                *suggestion.borrow_mut() =
                                    value["suggested_prompt"].as_str().unwrap_or("").to_string();
                                *report_recipe.borrow_mut() = value["recipe_path"]
                                    .as_str()
                                    .and_then(|path| std::fs::read(path).ok())
                                    .and_then(|raw| serde_json::from_slice(&raw).ok());
                                use_suggestion.set_sensitive(
                                    !suggestion.borrow().is_empty()
                                        && report_recipe.borrow().is_some(),
                                );
                            }
                        }
                    }
                }
                previous = raw;
            }
        }
        gtk::glib::ControlFlow::Continue
    });
    scroll(&page)
}

pub fn compare(snapshot: Snapshot, on_reuse: Reuse) -> gtk::Widget {
    let page = page("Compare runs");
    page.append(&label("Run a small, sequential sweep using the recipe in Create. Keep the seed fixed and change one variable. Each result retains its exact prompt, model, steps, sampler, timing and optional vision review."));
    let mode = gtk::DropDown::from_strings(&[
        "Prompt sweep · three lighting variations",
        "Step sweep · 8 (speed test), 16, 24",
        "Model comparison · installed SD 1.5 Q4 and Q8",
    ]);
    page.append(&mode);
    let review = gtk::CheckButton::with_label(
        "Review each result with Qwen vision after generation unloads",
    );
    page.append(&review);
    mode.update_property(&[gtk::accessible::Property::Label("Sweep type")]);
    let goal = gtk::Entry::new();
    goal.update_property(&[gtk::accessible::Property::Label("Sweep review goal")]);
    goal.set_placeholder_text(Some(
        "Review goal: clothing, warm lighting, natural expression…",
    ));
    page.append(&goal);
    let run_button = gtk::Button::with_label("Run sweep");
    run_button.add_css_class("suggested-action");
    run_button.set_halign(gtk::Align::Start);
    page.append(&run_button);
    let status = label(
        "Sweeps run one image at a time. Stop in the header cancels the current job and the remaining queue.",
    );
    page.append(&status);
    let results = gtk::ListBox::new();
    results.set_selection_mode(gtk::SelectionMode::None);
    results.add_css_class("boxed-list");
    page.append(&results);
    {
        let mode = mode.clone();
        let review = review.clone();
        let goal = goal.clone();
        let status = status.clone();
        run_button.connect_clicked(move |button| {
        let recipe=snapshot();let plan=serde_json::json!({"kind":match mode.selected(){0=>"lighting",1=>"steps",_=>"models"},"review":review.is_active(),"rubric":goal.text().to_string()});
        run(include_str!("sweep_runner.py"),vec![base().to_string_lossy().into_owned(),serde_json::to_string(&recipe).unwrap(),plan.to_string(),include_str!("local_generation.py").to_string(),include_str!("review_image.py").to_string()],&status,button);
    });
    }
    let mut previous = String::new();
    let weak = page.downgrade();
    gtk::glib::timeout_add_seconds_local(1, move || {
        if weak.upgrade().is_none() {
            return gtk::glib::ControlFlow::Break;
        }
        let raw = std::fs::read_to_string(base().join("latest-sweep.txt"))
            .ok()
            .and_then(|path| std::fs::read_to_string(path).ok());
        if let Some(raw) = raw {
            if raw != previous {
                if let Ok(manifest) = serde_json::from_str::<serde_json::Value>(&raw) {
                    status.set_text(&format!(
                        "{}{}",
                        manifest["status"].as_str().unwrap_or("Unknown"),
                        manifest["error"]
                            .as_str()
                            .map(|e| format!(": {e}"))
                            .unwrap_or_default()
                    ));
                    while let Some(child) = results.first_child() {
                        results.remove(&child);
                    }
                    if let Some(runs) = manifest["runs"].as_array() {
                        for item in runs {
                            let row = gtk::Box::new(gtk::Orientation::Horizontal, 12);
                            row.add_css_class("pantheon-inset");
                            if let Some(path) = item["image_path"].as_str() {
                                let picture = gtk::Picture::for_filename(path);
                                picture.set_size_request(160, 120);
                                picture.set_can_shrink(true);
                                picture.set_content_fit(gtk::ContentFit::Contain);
                                row.append(&picture);
                            }
                            let details = gtk::Box::new(gtk::Orientation::Vertical, 6);
                            details.set_hexpand(true);
                            details.append(&label(&format!(
                                "{} · {}",
                                item["label"].as_str().unwrap_or("Run"),
                                item["status"].as_str().unwrap_or("Unknown")
                            )));
                            details.append(&label(&format!(
                                "Time: {} · Peak process RSS: {} · Vision score: {}",
                                item["elapsed_seconds"]
                                    .as_f64()
                                    .map(|v| format!("{v:.1} s"))
                                    .unwrap_or_else(|| "Not measured".into()),
                                item["peak_memory_mib"]
                                    .as_u64()
                                    .map(|v| format!("{v} MiB"))
                                    .unwrap_or_else(|| "Not measured".into()),
                                item["overall_score"]
                                    .as_f64()
                                    .map(|v| format!("{v:.2}/5 (advisory)"))
                                    .unwrap_or_else(|| "Not reviewed".into())
                            )));
                            if let Some(error) =
                                item["error"].as_str().or(item["review_error"].as_str())
                            {
                                details.append(&label(error));
                            }
                            if let Some(path) = item["recipe_path"].as_str() {
                                if let Ok(raw) = std::fs::read(path) {
                                    if let Ok(recipe) = serde_json::from_slice::<Recipe>(&raw) {
                                        let reuse = gtk::Button::with_label("Use this run");
                                        reuse.set_halign(gtk::Align::Start);
                                        let on_reuse = on_reuse.clone();
                                        reuse.connect_clicked(move |_| on_reuse(&recipe));
                                        details.append(&reuse);
                                    }
                                }
                            }
                            row.append(&details);
                            results.append(&row);
                        }
                    }
                }
                previous = raw;
            }
        }
        gtk::glib::ControlFlow::Continue
    });
    scroll(&page)
}
