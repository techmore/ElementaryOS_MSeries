// SPDX-License-Identifier: GPL-3.0-or-later
#include <xf86drm.h>
#include <xf86drmMode.h>
#include <fcntl.h>
#include <stdio.h>
#include <unistd.h>
#include <string.h>
static void props(int fd, uint32_t id, uint32_t type) {
    drmModeObjectPropertiesPtr ps = drmModeObjectGetProperties(fd,id,type);
    if (!ps) return;
    for (uint32_t i=0;i<ps->count_props;i++) {
        drmModePropertyPtr p = drmModeGetProperty(fd,ps->props[i]);
        if (!p) continue;
        if (!strcmp(p->name,"VRR_ENABLED") || !strcmp(p->name,"vrr_capable") || !strcmp(p->name,"ACTIVE") || !strcmp(p->name,"CRTC_ID"))
            printf(" %s=%llu",p->name,(unsigned long long)ps->prop_values[i]);
        drmModeFreeProperty(p);
    }
    drmModeFreeObjectProperties(ps);
}
int main(int argc, char **argv) {
    if (argc != 2) {
        fprintf(stderr, "Usage: %s /dev/dri/cardN\n", argv[0]);
        return 2;
    }
    int fd=open(argv[1],O_RDONLY|O_CLOEXEC);
    if(fd<0) {perror("open");return 1;}
    drmModeResPtr r=drmModeGetResources(fd);
    if(!r) {perror("resources");close(fd);return 1;}
    for(int i=0;i<r->count_connectors;i++) {
        drmModeConnectorPtr c=drmModeGetConnectorCurrent(fd,r->connectors[i]);
        if(!c) continue;
        printf("connector %u %s-%u connected=%d",c->connector_id,drmModeGetConnectorTypeName(c->connector_type),c->connector_type_id,c->connection==DRM_MODE_CONNECTED);
        props(fd,c->connector_id,DRM_MODE_OBJECT_CONNECTOR);puts("");
        drmModeFreeConnector(c);
    }
    for(int i=0;i<r->count_crtcs;i++) {
        drmModeCrtcPtr c=drmModeGetCrtc(fd,r->crtcs[i]);
        if(!c) continue;
        printf("crtc %u mode=%s refresh=%u valid=%d",c->crtc_id,c->mode.name,c->mode.vrefresh,c->mode_valid);
        props(fd,c->crtc_id,DRM_MODE_OBJECT_CRTC);puts("");
        drmModeFreeCrtc(c);
    }
    drmModeFreeResources(r);close(fd);return 0;
}
