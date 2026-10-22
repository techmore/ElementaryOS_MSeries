// SPDX-License-Identifier: GPL-2.0-only
/* QEMU-only shared scheduler callback-module lifetime fixture. No hardware IO. */
#include <linux/module.h>
#include <linux/moduleparam.h>
#include <linux/device/faux.h>
#include <linux/dma-fence.h>
#include <linux/refcount.h>
#include <linux/slab.h>
#include <drm/gpu_scheduler.h>

struct allocation {
	struct drm_gpu_scheduler sched;
	refcount_t refs;
};
struct fixture_job {
	struct drm_sched_job job;
	struct allocation *allocation;
};
struct fixture_fence {
	struct dma_fence fence;
	spinlock_t lock;
};
static struct faux_device *fixture_device;
static struct fixture_fence *dependency;
static atomic_t completed = ATOMIC_INIT(0);
static atomic_t unexpected_runs = ATOMIC_INIT(0);
static atomic_t released = ATOMIC_INIT(0);

static const char *fence_name(struct dma_fence *fence)
{
	return "m4-sched-module-fixture";
}
static void fence_release(struct dma_fence *fence)
{
	kfree(container_of(fence, struct fixture_fence, fence));
}
static const struct dma_fence_ops fence_ops = {
	.get_driver_name = fence_name,
	.get_timeline_name = fence_name,
	.release = fence_release,
};
static void allocation_put(struct allocation *allocation)
{
	if (refcount_dec_and_test(&allocation->refs))
		kfree(allocation);
}
static struct dma_fence *run_job(struct drm_sched_job *job)
{
	atomic_inc(&unexpected_runs);
	return NULL;
}
static enum drm_gpu_sched_stat timed_out(struct drm_sched_job *job)
{
	atomic_inc(&unexpected_runs);
	return DRM_GPU_SCHED_STAT_ENODEV;
}
static void free_job(struct drm_sched_job *base)
{
	struct fixture_job *job = container_of(base, struct fixture_job, job);
	struct allocation *allocation = job->allocation;

	drm_sched_job_cleanup(base);
	kfree(job);
	allocation_put(allocation);
	atomic_set(&completed, 1);
	pr_info("M4_SCHED_MODULE_JOB_RELEASED\n");
	/* The C core drops its module reference only after this callback returns. */
}
static const struct drm_sched_backend_ops backend_ops = {
	.run_job = run_job,
	.timedout_job = timed_out,
	.free_job = free_job,
	.retain_job_on_enodev = true,
	.owner = THIS_MODULE,
};
static int release_set(const char *value, const struct kernel_param *parameter)
{
	bool signal;
	int error = kstrtobool(value, &signal);

	if (error)
		return error;
	if (!dependency)
		return -EAGAIN;
	if (signal && atomic_cmpxchg(&released, 0, 1) == 0)
		dma_fence_signal(&dependency->fence);
	return 0;
}
static int done_get(char *buffer, const struct kernel_param *parameter)
{
	return scnprintf(buffer, PAGE_SIZE, "%d\n", atomic_read(&completed));
}
static int runs_get(char *buffer, const struct kernel_param *parameter)
{
	return scnprintf(buffer, PAGE_SIZE, "%d\n", atomic_read(&unexpected_runs));
}
static const struct kernel_param_ops release_ops = { .set = release_set };
static const struct kernel_param_ops done_ops = { .get = done_get };
static const struct kernel_param_ops runs_ops = { .get = runs_get };
module_param_cb(release, &release_ops, NULL, 0200);
module_param_cb(done, &done_ops, NULL, 0444);
module_param_cb(runs, &runs_ops, NULL, 0444);

static int __init fixture_init(void)
{
	struct drm_sched_entity entity;
	struct allocation *allocation;
	struct drm_gpu_scheduler *sched;
	struct fixture_job *job;
	struct drm_sched_init_args args = {
		.ops = &backend_ops,
		.num_rqs = 1,
		.credit_limit = 1,
		.timeout = MAX_SCHEDULE_TIMEOUT,
		.name = "m4-sched-module-fixture",
	};
	int error;

	fixture_device = faux_device_create("m4-sched-module-fixture", NULL, NULL);
	if (!fixture_device)
		return -ENOMEM;
	dependency = kzalloc(sizeof(*dependency), GFP_KERNEL);
	if (!dependency) {
		error = -ENOMEM;
		goto destroy_device;
	}
	spin_lock_init(&dependency->lock);
	dma_fence_init(&dependency->fence, &fence_ops, &dependency->lock,
		       dma_fence_context_alloc(1), 1);
	allocation = kzalloc(sizeof(*allocation), GFP_KERNEL);
	if (!allocation) {
		error = -ENOMEM;
		goto put_dependency;
	}
	refcount_set(&allocation->refs, 1);
	sched = &allocation->sched;
	args.dev = &fixture_device->dev;
	error = drm_sched_init(sched, &args);
	if (error)
		goto put_allocation;
	error = drm_sched_entity_init(&entity, DRM_SCHED_PRIORITY_KERNEL, &sched, 1, NULL);
	if (error)
		goto finish_scheduler;
	job = kzalloc(sizeof(*job), GFP_KERNEL);
	if (!job) {
		error = -ENOMEM;
		goto finish_entity;
	}
	error = drm_sched_job_init(&job->job, &entity, 1, NULL, 0);
	if (error)
		goto free_uninitialized_job;
	refcount_inc(&allocation->refs);
	job->allocation = allocation;
	error = drm_sched_job_add_dependency(&job->job, dma_fence_get(&dependency->fence));
	if (error) {
		drm_sched_job_cleanup(&job->job);
		allocation_put(allocation);
		goto free_uninitialized_job;
	}
	drm_sched_job_arm(&job->job);
	drm_sched_entity_push_job(&job->job);
	/* Force killed-entity cleanup without waiting for the unsignalled dependency. */
	drm_sched_entity_fini(&entity);
	drm_sched_fini(sched);
	allocation_put(allocation);
	pr_info("M4_SCHED_MODULE_READY done=%d runs=%d\n",
		atomic_read(&completed), atomic_read(&unexpected_runs));
	return 0;

free_uninitialized_job:
	kfree(job);
finish_entity:
	drm_sched_entity_fini(&entity);
finish_scheduler:
	drm_sched_fini(sched);
put_allocation:
	allocation_put(allocation);
put_dependency:
	dma_fence_put(&dependency->fence);
	dependency = NULL;
destroy_device:
	faux_device_destroy(fixture_device);
	return error;
}
static void __exit fixture_exit(void)
{
	WARN_ON(atomic_read(&completed) != 1);
	WARN_ON(atomic_read(&unexpected_runs) != 0);
	dma_fence_put(&dependency->fence);
	dependency = NULL;
	faux_device_destroy(fixture_device);
	pr_info("M4_SCHED_MODULE_EXIT\n");
}
module_init(fixture_init);
module_exit(fixture_exit);
MODULE_LICENSE("GPL");
MODULE_DESCRIPTION("QEMU-only deferred scheduler callback module lifetime fixture");
