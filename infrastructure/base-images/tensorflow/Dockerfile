# ==============================================================================
# ZH: aibase/tensorflow:2026-spring — TensorFlow 2.15 + GPU
# EN: aibase/tensorflow:2026-spring — TensorFlow 2.15 + GPU support
# ==============================================================================

FROM aibase/common-tools:2026-spring

USER root

# TF 2.15 with GPU support (CUDA 12.3+ compatible)
RUN pip install --no-cache-dir \
        tensorflow[and-cuda]==2.15.0 \
        keras==2.15.0 \
        tensorboard \
    && pip install --no-cache-dir \
        numpy pandas matplotlib seaborn scikit-learn \
        tqdm rich \
        jupyter ipython ipykernel \
        Pillow opencv-python-headless

USER coder

RUN python -m ipykernel install --user --name aibase-tf --display-name "AI Base TensorFlow 2.15"

LABEL org.opencontainers.image.title="AI Base TensorFlow" \
      aibase.framework="tensorflow" \
      aibase.framework_version="2.15"

CMD ["/bin/bash"]
