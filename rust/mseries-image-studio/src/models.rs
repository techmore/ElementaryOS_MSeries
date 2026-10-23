use gtk::prelude::*;
use std::path::Path;

pub fn storage_bytes(path: &Path) -> u64 {
    let Ok(entries) = std::fs::read_dir(path) else {
        return 0;
    };
    entries
        .flatten()
        .map(|e| {
            let Ok(m) = e.path().symlink_metadata() else {
                return 0;
            };
            if m.is_symlink() {
                0
            } else if m.is_dir() {
                storage_bytes(&e.path())
            } else {
                m.len()
            }
        })
        .sum()
}

pub fn storage_label() -> gtk::Label {
    let label = gtk::Label::new(Some("Measuring storage…"));
    label.set_wrap(true);
    label.set_xalign(0.0);
    let (tx, rx) = std::sync::mpsc::channel();
    let base = gtk::glib::user_data_dir();
    std::thread::spawn(move || {
        loop {
            let models = storage_bytes(&base.join("mseries-image-studio/models"));
            let shared = storage_bytes(&base.join("mseries-ai/models"));
            let images = storage_bytes(&base.join("mseries-image-studio/images"))
                + storage_bytes(&base.join("mseries-image-studio/previews"));
            let engine = storage_bytes(&base.join("mseries-image-studio/engine"))
                + storage_bytes(&base.join("mseries-image-studio/engine-source"));
            if tx
                .send(format!(
                    "Models  {:.2} GiB\nOther AI  {:.2} GiB\nImages  {:.1} MiB\nEngine  {:.2} GiB",
                    models as f64 / 1073741824.0,
                    shared as f64 / 1073741824.0,
                    images as f64 / 1048576.0,
                    engine as f64 / 1073741824.0
                ))
                .is_err()
            {
                break;
            }
            std::thread::sleep(std::time::Duration::from_secs(5));
        }
    });
    let weak = label.downgrade();
    gtk::glib::timeout_add_seconds_local(1, move || {
        let Some(label) = weak.upgrade() else {
            return gtk::glib::ControlFlow::Break;
        };
        while let Ok(s) = rx.try_recv() {
            label.set_text(&s);
        }
        gtk::glib::ControlFlow::Continue
    });
    label
}

pub fn page(on_select: std::rc::Rc<dyn Fn(&str)>) -> gtk::Widget {
    let page = gtk::Box::new(gtk::Orientation::Vertical, 16);
    page.add_css_class("pantheon-inset");
    let title = gtk::Label::new(Some("Models for this Mac"));
    title.add_css_class("title-2");
    title.set_xalign(0.0);
    page.append(&title);
    let note = gtk::Label::new(Some(
        "Apple Silicon · Linux ARM64 / Vulkan target. These compact downloads fit the disk budget; actual inference memory and GPU support still need qualification. macOS-only Metal / MLX packages are excluded.",
    ));
    note.set_wrap(true);
    note.set_xalign(0.0);
    page.append(&note);
    page.append(&storage_label());
    let choices = gtk::DropDown::from_strings(&[
        "Stable Diffusion 1.5 · Q4 · 1.57 GB",
        "Stable Diffusion 1.5 · Q8 · 1.76 GB",
        "SDXL Turbo · FP16 · 6.94 GB",
        "Qwen3-VL 2B + projector · review images · 1.55 GB",
        "Realistic Vision V6 FP16 + VAE · photography · 2.47 GB",
        "Reference appearance · IP-Adapter Plus Face + vision encoder · 3.9 GB",
    ]);
    page.append(&choices);
    let requirements = gtk::Label::new(Some(
        "SD 1.5 Q4: estimated 3 GiB worker budget plus 6 GiB desktop reserve. Start with Euler, 20 steps, guidance 7, 512 × 512. LoRAs must match SD 1.5.",
    ));
    requirements.set_wrap(true);
    requirements.set_xalign(0.0);
    page.append(&requirements);
    choices.connect_selected_notify(move |choices| {
        requirements.set_text(match choices.selected() {
            0 => "SD 1.5 Q4: estimated 3 GiB worker budget plus 6 GiB desktop reserve. Euler, 20 steps, guidance 7, 512 × 512. Good first calibration candidate.",
            1 => "SD 1.5 Q8: estimated 3.5 GiB worker budget plus 6 GiB reserve. Same starter settings as Q4; use Compare to measure quality and speed differences.",
            2 => "SDXL Turbo: estimated 6 GiB worker budget plus 6 GiB reserve. Euler ancestral, 4 steps, engine guidance 1, no negative prompt, 512 × 512. Commercial use needs the applicable model license.",
            4 => "Realistic Vision V6: photographic portrait candidate. Downloads the full FP16 checkpoint and required VAE. Start at 512 × 768, 30 DPM++2M steps, Karras, CFG 5. Local image-quality validation is in progress.",
            5 => "Reference appearance bundle: SD 1.5 Plus Face adapter and CLIP vision encoder, converted to FP16 locally. Apache 2.0. Requires an installed engine, about 3.9 GB disk plus reserve, and separate inference-memory qualification. Not an image-generation checkpoint.",
            _ => "Qwen3-VL 2B: image reviewer, not an image generator. Downloads both the language weights and matching Q8 vision projector. Uses a separate CPU worker after image generation unloads. Requires 9 GiB available.",
        });
    });
    let license = gtk::Label::new(Some(
        "SD 1.5: CreativeML Open RAIL-M · SDXL Turbo: Stability AI non-commercial community license. Review the model license before commercial fashion use.",
    ));
    license.set_wrap(true);
    license.set_xalign(0.0);
    page.append(&license);
    let button = gtk::Button::with_label("Download selected model");
    button.add_css_class("suggested-action");
    button.set_halign(gtk::Align::Start);
    page.append(&button);
    let cancel_download = gtk::Button::with_label("Cancel download");
    cancel_download.set_halign(gtk::Align::Start);
    cancel_download.connect_clicked(move |_| {
        let directory = gtk::glib::user_data_dir().join("mseries-image-studio/models");
        let _ = std::fs::create_dir_all(&directory);
        let _ = std::fs::write(directory.join("download.cancel"), "cancel");
    });
    page.append(&cancel_download);
    let use_model = gtk::Button::with_label("Use selected model");
    use_model.set_halign(gtk::Align::Start);
    page.append(&use_model);
    let status = gtk::Label::new(Some(
        "Downloads verify file size and SHA-256, and keep 2 GiB of disk space free. Installing a model does not qualify inference.",
    ));
    status.set_wrap(true);
    status.set_xalign(0.0);
    page.append(&status);
    {
        let choices = choices.clone();
        let status = status.clone();
        use_model.connect_clicked(move |_| {
            if choices.selected() == 5 {
                status.set_text("Reference bundle is used with an SD 1.5 checkpoint; choose a reference image in Create after download.");
                return;
            }
            let names = [
                "stable-diffusion-v1-5-pruned-emaonly-Q4_0.gguf",
                "stable-diffusion-v1-5-pruned-emaonly-Q8_0.gguf",
                "sd_xl_turbo_1.0_fp16.safetensors",
                "Qwen3VL-2B-Instruct-Q4_K_M.gguf",
                "Realistic_Vision_V6.0_NV_B1_fp16.safetensors",
            ];
            let file = gtk::glib::user_data_dir()
                .join("mseries-image-studio/models")
                .join(names[choices.selected().min(4) as usize]);
            if file.is_file() {
                on_select(&file.to_string_lossy());
            } else {
                status.set_text("Download the selected model first.");
            }
        });
    }
    let install = gtk::Button::with_label("Install or rebuild local image engine");
    install.set_halign(gtk::Align::Start);
    page.append(&install);
    let engine_status = gtk::Label::new(Some(
        "Requires Git, CMake, a C++ compiler and Vulkan development tools. Builds the pinned engine with two compiler jobs.",
    ));
    engine_status.set_wrap(true);
    engine_status.set_xalign(0.0);
    page.append(&engine_status);
    install.connect_clicked(move |button| {
        button.set_sensitive(false);
        engine_status.set_text("Preparing the local engine… This can take several minutes.");
        let directory = gtk::glib::user_data_dir().join("mseries-image-studio");
        let (tx, rx) = std::sync::mpsc::channel();
        std::thread::spawn(move || {
            let result = std::process::Command::new("python3")
                .arg("-c")
                .arg(include_str!("install_engine.py"))
                .arg(directory)
                .output();
            let message = match result {
                Ok(out) if out.status.success() => {
                    "Engine installed. Use a model starter preset to begin calibration.".to_string()
                }
                Ok(out) => String::from_utf8_lossy(&out.stderr)
                    .chars()
                    .rev()
                    .take(3000)
                    .collect::<String>()
                    .chars()
                    .rev()
                    .collect(),
                Err(error) => error.to_string(),
            };
            let _ = tx.send(message);
        });
        let button = button.clone();
        let status = engine_status.clone();
        gtk::glib::timeout_add_seconds_local(1, move || {
            if let Ok(message) = rx.try_recv() {
                status.set_text(&message);
                button.set_sensitive(true);
                gtk::glib::ControlFlow::Break
            } else {
                gtk::glib::ControlFlow::Continue
            }
        });
    });
    let progress = gtk::Label::new(None);
    progress.set_wrap(true);
    progress.set_xalign(0.0);
    page.append(&progress);
    let weak_progress = progress.downgrade();
    gtk::glib::timeout_add_seconds_local(1, move || {
        let Some(progress) = weak_progress.upgrade() else {
            return gtk::glib::ControlFlow::Break;
        };
        let path =
            gtk::glib::user_data_dir().join("mseries-image-studio/models/download-progress.json");
        if let Ok(raw) = std::fs::read(path) {
            if let Ok(value) = serde_json::from_slice::<serde_json::Value>(&raw) {
                progress.set_text(&format!(
                    "{} · {} · {:.1} / {:.1} MiB",
                    value["file"].as_str().unwrap_or("Model"),
                    value["phase"].as_str().unwrap_or("Unknown"),
                    value["received"].as_u64().unwrap_or(0) as f64 / 1048576.0,
                    value["total"].as_u64().unwrap_or(0) as f64 / 1048576.0
                ));
            }
        }
        gtk::glib::ControlFlow::Continue
    });
    let choices_for_download = choices.clone();
    button.connect_clicked(move |button| {
        let choices = choices_for_download.clone();
        button.set_sensitive(false);
        choices.set_sensitive(false);
        status.set_text("Downloading and verifying… Storage totals include partial downloads.");
        let index = choices.selected();
        let directory = gtk::glib::user_data_dir().join("mseries-image-studio/models");
        let _ = std::fs::remove_file(directory.join("download.cancel"));
        let (tx, rx) = std::sync::mpsc::channel();
        std::thread::spawn(move || {
            if index == 5 {
                let message = match std::process::Command::new("python3")
                    .arg("-c")
                    .arg(REFERENCE_BUNDLE_DOWNLOAD)
                    .arg(&directory)
                    .output()
                {
                    Ok(out) => format!(
                        "{}{}",
                        String::from_utf8_lossy(&out.stdout),
                        String::from_utf8_lossy(&out.stderr)
                    ),
                    Err(error) => error.to_string(),
                };
                let _ = tx.send(message);
                return;
            }
            if index == 3 || index == 4 {
                let mut messages = Vec::new();
                let bundle = if index == 3 {
                    [
                        (
                            "Qwen/Qwen3-VL-2B-Instruct-GGUF",
                            "Qwen3VL-2B-Instruct-Q4_K_M.gguf",
                        ),
                        (
                            "Qwen/Qwen3-VL-2B-Instruct-GGUF",
                            "mmproj-Qwen3VL-2B-Instruct-Q8_0.gguf",
                        ),
                    ]
                } else {
                    [
                        (
                            "SG161222/Realistic_Vision_V6.0_B1_noVAE",
                            "Realistic_Vision_V6.0_NV_B1_fp16.safetensors",
                        ),
                        (
                            "stabilityai/sd-vae-ft-mse-original",
                            "vae-ft-mse-840000-ema-pruned.safetensors",
                        ),
                    ]
                };
                for (repo, file) in bundle {
                    match std::process::Command::new("python3")
                        .arg("-c")
                        .arg(include_str!("download_model.py"))
                        .args([repo, file])
                        .arg(&directory)
                        .output()
                    {
                        Ok(output) => {
                            messages.push(String::from_utf8_lossy(&output.stdout).to_string());
                            if !output.status.success() {
                                break;
                            }
                        }
                        Err(error) => {
                            messages.push(error.to_string());
                            break;
                        }
                    }
                }
                let _ = tx.send(messages.join("\n"));
                return;
            }
            let (repo, file) = match index {
                0 => (
                    "second-state/stable-diffusion-v1-5-GGUF",
                    "stable-diffusion-v1-5-pruned-emaonly-Q4_0.gguf",
                ),
                1 => (
                    "second-state/stable-diffusion-v1-5-GGUF",
                    "stable-diffusion-v1-5-pruned-emaonly-Q8_0.gguf",
                ),
                _ => ("stabilityai/sdxl-turbo", "sd_xl_turbo_1.0_fp16.safetensors"),
            };
            let result = std::process::Command::new("python3")
                .arg("-c")
                .arg(include_str!("download_model.py"))
                .args([repo, file])
                .arg(directory)
                .output();
            let text = match result {
                Ok(out) => format!(
                    "{}{}",
                    String::from_utf8_lossy(&out.stdout),
                    String::from_utf8_lossy(&out.stderr)
                ),
                Err(e) => e.to_string(),
            };
            let _ = tx.send(text);
        });
        let button = button.clone();
        let choices = choices.clone();
        let status = status.clone();
        gtk::glib::timeout_add_seconds_local(1, move || {
            if let Ok(text) = rx.try_recv() {
                status.set_text(&text);
                button.set_sensitive(true);
                choices.set_sensitive(true);
                gtk::glib::ControlFlow::Break
            } else {
                gtk::glib::ControlFlow::Continue
            }
        });
    });
    gtk::ScrolledWindow::builder()
        .child(&page)
        .hscrollbar_policy(gtk::PolicyType::Never)
        .build()
        .upcast()
}

// Runs on the downloader worker thread, never on GTK's main loop.
const REFERENCE_BUNDLE_DOWNLOAD: &str = r#"
import os,sys,json,hashlib,urllib.request,subprocess,time,shutil
from pathlib import Path
os.umask(0o077)
dest=Path(sys.argv[1]);dest.mkdir(parents=True,exist_ok=True)
base=dest.parent;revision='018e402774aeeddd60609b4ecdb7e298259dc729'
cancel=dest/'download.cancel';lock=dest/'reference-download.lock';owned=False
engine_revision='fd21ecfceef2665d2c5f2db8536e3202d864fd30'
def publish(phase,name='Reference appearance bundle',received=0,total=0):
    tmp=dest/'download-progress.reference.tmp'
    tmp.write_text(json.dumps(dict(file=name,phase=phase,received=received,total=total)))
    os.replace(tmp,dest/'download-progress.json')
def cancelled():
    if cancel.exists():raise RuntimeError('Reference download or conversion cancelled.')
def digest(path):
    h=hashlib.sha256()
    with path.open('rb') as f:
        while True:
            cancelled();chunk=f.read(1024*1024)
            if not chunk:break
            h.update(chunk)
    return h.hexdigest()
def receipt(path,data):
    tmp=path.with_suffix(path.suffix+'.receipt.tmp');tmp.write_text(json.dumps(data,indent=2));os.replace(tmp,path.with_suffix(path.suffix+'.json'))
try:
    fd=os.open(lock,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600);os.close(fd);owned=True
    cancelled()
    binary=base/'engine/sd-cli'
    source=json.loads((base/'engine/source.json').read_text())
    if source.get('revision')!=engine_revision or not binary.is_file():raise RuntimeError('Install the pinned local engine before the reference bundle.')
    if (base/'generation.lock').exists() or (base/'batch.lock').exists():raise RuntimeError('Wait for the active generation or comparison before conversion.')
    for remote,name in [('models/image_encoder/model.safetensors','clip-vision-h.safetensors'),('models/ip-adapter-plus-face_sd15.safetensors','ip-adapter-plus-face_sd15.safetensors')]:
        cancelled();publish('Reading pinned metadata',name)
        with urllib.request.urlopen('https://huggingface.co/api/models/h94/IP-Adapter/revision/'+revision+'?blobs=true',timeout=30) as response:info=json.load(response)
        entry=next(x for x in info['siblings'] if x['rfilename']==remote);size=entry['lfs']['size'];expected=entry['lfs']['sha256']
        target=dest/name;part=dest/(name+'.reference.part')
        if target.exists():
            if target.stat().st_size!=size or digest(target)!=expected:raise RuntimeError('Existing '+name+' differs from pinned source; preserved without overwrite.')
        else:
            if shutil.disk_usage(dest).free<size+int(1.4*1024**3)+2*1024**3:raise RuntimeError('Insufficient storage including conversion and 2 GiB disk reserve.')
            try:
                received=0;last=0
                with urllib.request.urlopen('https://huggingface.co/h94/IP-Adapter/resolve/'+revision+'/'+remote,timeout=60) as response,part.open('xb') as stream:
                    while True:
                        cancelled();chunk=response.read(1024*1024)
                        if not chunk:break
                        stream.write(chunk);received+=len(chunk)
                        if received>size:raise RuntimeError('Source exceeded declared size.')
                        if time.monotonic()-last>1:publish('Downloading',name,received,size);last=time.monotonic()
                if received!=size or digest(part)!=expected:raise RuntimeError('Reference integrity verification failed.')
                os.replace(part,target)
            finally:part.unlink(missing_ok=True)
        receipt(target,dict(repo='h94/IP-Adapter',revision=revision,source_path=remote,sha256=expected,size=size,license='apache-2.0',qualified=False))
    encoder=dest/'clip-vision-h.safetensors';output=dest/'clip-vision-h-f16.gguf';partial=dest/'clip-vision-h-f16.reference.tmp.gguf'
    source_sha=digest(encoder)
    if output.exists():
        saved=json.loads(output.with_suffix(output.suffix+'.json').read_text())
        if saved.get('source_sha256')!=source_sha or saved.get('engine_revision')!=engine_revision or saved.get('sha256')!=digest(output):raise RuntimeError('Existing converted encoder has no matching verified receipt; preserved.')
    else:
        available=next(int(line.split()[1])*1024 for line in Path('/proc/meminfo').read_text().splitlines() if line.startswith('MemAvailable:'))
        if available<9*1024**3:raise RuntimeError('FP16 conversion needs 9 GiB available including the protected desktop reserve.')
        publish('Converting vision encoder to FP16; cancellation remains available')
        command=[str(binary),'-M','convert','-m',str(encoder),'--type','f16','-o',str(partial)]
        try:
            with (dest/'reference-conversion.log').open('w') as log:
                proc=subprocess.Popen(command,stdout=log,stderr=log)
                try:
                    while proc.poll() is None:cancelled();time.sleep(0.25)
                finally:
                    if proc.poll() is None:
                        proc.terminate()
                        try:proc.wait(timeout=5)
                        except subprocess.TimeoutExpired:proc.kill();proc.wait()
                if proc.returncode!=0:raise RuntimeError('Vision conversion failed; see reference-conversion.log.')
            cancelled()
            if not partial.is_file() or partial.stat().st_size==0:raise RuntimeError('Conversion produced no encoder.')
            converted_sha=digest(partial);os.replace(partial,output)
            receipt(output,dict(source_sha256=source_sha,source_revision=revision,engine_revision=engine_revision,engine_sha256=digest(binary),sha256=converted_sha,size=output.stat().st_size,conversion=command,qualified=False))
        finally:partial.unlink(missing_ok=True)
    publish('Reference bundle verified; inference qualification required')
    print('Reference appearance bundle installed and verified. Select an SD 1.5 checkpoint and reference image; memory qualification is still required.')
except Exception as error:
    publish('Unavailable: '+str(error));print(str(error),file=sys.stderr);sys.exit(1)
finally:
    if owned:lock.unlink(missing_ok=True)
"#;
