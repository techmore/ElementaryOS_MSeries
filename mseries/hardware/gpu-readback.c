// SPDX-License-Identifier: GPL-3.0-or-later
/* Small surfaceless GLES2 shader/readback test. No display modes or audio. */
#include <EGL/egl.h>
#include <GLES2/gl2.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static GLuint shader(GLenum type, const char *source) {
    GLuint object = glCreateShader(type);
    glShaderSource(object, 1, &source, NULL);
    glCompileShader(object);
    GLint status;
    glGetShaderiv(object, GL_COMPILE_STATUS, &status);
    if (!status) { fputs("shader compilation failed\n", stderr); exit(1); }
    return object;
}

int main(void) {
    EGLDisplay display = eglGetPlatformDisplay(0x31DD /* SURFACELESS_MESA */, EGL_DEFAULT_DISPLAY, NULL);
    EGLint major, minor, count;
    const EGLint attributes[] = {EGL_SURFACE_TYPE, EGL_PBUFFER_BIT, EGL_RENDERABLE_TYPE, EGL_OPENGL_ES2_BIT,
        EGL_RED_SIZE, 8, EGL_GREEN_SIZE, 8, EGL_BLUE_SIZE, 8, EGL_ALPHA_SIZE, 8, EGL_NONE};
    EGLConfig config;
    if (display == EGL_NO_DISPLAY || !eglInitialize(display, &major, &minor) ||
        !eglBindAPI(EGL_OPENGL_ES_API) || !eglChooseConfig(display, attributes, &config, 1, &count) || !count) {
        fprintf(stderr, "EGL initialization failed: %#x\n", eglGetError()); return 1;
    }
    const EGLint surface_attributes[] = {EGL_WIDTH, 4, EGL_HEIGHT, 4, EGL_NONE};
    const EGLint context_attributes[] = {EGL_CONTEXT_CLIENT_VERSION, 2, EGL_NONE};
    EGLSurface surface = eglCreatePbufferSurface(display, config, surface_attributes);
    EGLContext context = eglCreateContext(display, config, EGL_NO_CONTEXT, context_attributes);
    if (surface == EGL_NO_SURFACE || context == EGL_NO_CONTEXT || !eglMakeCurrent(display, surface, surface, context)) {
        fprintf(stderr, "EGL context failed: %#x\n", eglGetError()); return 1;
    }
    const char *renderer = (const char *)glGetString(GL_RENDERER);
    const char *version = (const char *)glGetString(GL_VERSION);
    if (!renderer || !version || !strstr(renderer, "Apple") || !strstr(renderer, "M1") || strstr(renderer, "llvmpipe")) {
        fprintf(stderr, "not the expected M1 hardware renderer: %s\n", renderer ? renderer : "unknown"); return 1;
    }
    GLuint vertex = shader(GL_VERTEX_SHADER, "attribute vec2 position; void main(){gl_Position=vec4(position,0.,1.);}");
    GLuint fragment = shader(GL_FRAGMENT_SHADER, "precision mediump float; void main(){gl_FragColor=vec4(.25,.5,.75,1.);}");
    GLuint program = glCreateProgram();
    glAttachShader(program, vertex); glAttachShader(program, fragment);
    glBindAttribLocation(program, 0, "position"); glLinkProgram(program);
    GLint linked; glGetProgramiv(program, GL_LINK_STATUS, &linked);
    if (!linked) { fputs("shader link failed\n", stderr); return 1; }
    const GLfloat vertices[] = {-1., -1., 3., -1., -1., 3.};
    GLuint buffer; glGenBuffers(1, &buffer); glBindBuffer(GL_ARRAY_BUFFER, buffer);
    glBufferData(GL_ARRAY_BUFFER, sizeof(vertices), vertices, GL_STATIC_DRAW);
    glVertexAttribPointer(0, 2, GL_FLOAT, GL_FALSE, 0, NULL); glEnableVertexAttribArray(0);
    glViewport(0, 0, 4, 4); glUseProgram(program); glDrawArrays(GL_TRIANGLES, 0, 3);
    unsigned char pixels[64]; glReadPixels(0, 0, 4, 4, GL_RGBA, GL_UNSIGNED_BYTE, pixels);
    if (glGetError() != GL_NO_ERROR) { fputs("GLES draw/readback error\n", stderr); return 1; }
    const int expected[] = {64, 128, 191, 255};
    for (int pixel = 0; pixel < 16; pixel++)
        for (int channel = 0; channel < 4; channel++)
            if (abs((int)pixels[pixel * 4 + channel] - expected[channel]) > 1) {
                fprintf(stderr, "pixel %d channel %d mismatch\n", pixel, channel); return 1;
            }
    printf("renderer=%s\nversion=%s\nverified_pixels=16\n", renderer, version);
    glDeleteBuffers(1, &buffer); glDeleteProgram(program); glDeleteShader(vertex); glDeleteShader(fragment);
    eglMakeCurrent(display, EGL_NO_SURFACE, EGL_NO_SURFACE, EGL_NO_CONTEXT);
    eglDestroyContext(display, context); eglDestroySurface(display, surface); eglTerminate(display);
    return 0;
}
