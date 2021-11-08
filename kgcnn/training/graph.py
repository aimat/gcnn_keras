import tensorflow as tf
import matplotlib.pyplot as plt
import numpy as np
import time
import os

from tensorflow_addons import optimizers
from kgcnn.utils import learning
from kgcnn.utils.loss import ScaledMeanAbsoluteError, ScaledRootMeanSquaredError
from sklearn.model_selection import KFold
from kgcnn.hyper.selection import HyperSelection
from datetime import timedelta
from kgcnn.io.loader import NumpyTensorList


def train_graph_regression_supervised(X_train, y_train,
                                      validation_data,
                                      make_model,
                                      hyper_selection,
                                      scaler,
                                      ):
    # Hyper-parameter via hyper_selection
    assert isinstance(hyper_selection, HyperSelection), "ERROR:kgcnn: Error require valid `HyperSelection`."

    # Make model.
    model = make_model(**hyper_selection.make_model())

    # Get optimizer from serialized hyper-parameter.
    mae_metric = ScaledMeanAbsoluteError((1, 1), name='mean_absolute_error')
    rms_metric = ScaledRootMeanSquaredError((1, 1))
    if scaler.scale_ is not None:
        mae_metric.set_scale(np.expand_dims(scaler.scale_, axis=0))
        rms_metric.set_scale(np.expand_dims(scaler.scale_, axis=0))
    model.compile(**hyper_selection.compile(loss='mean_squared_error', metrics=[mae_metric, rms_metric]))
    print(model.summary())

    # Start and time training
    start = time.process_time()
    hist = model.fit(X_train, y_train,
                     validation_data=validation_data,
                     **hyper_selection.fit()
                     )
    stop = time.process_time()
    print("Print Time for training: ", str(timedelta(seconds=stop - start)))

    return model, hist


def train_graph_classification_supervised(X_train, y_train,
                                        validation_data,
                                          make_model,
                                          hyper_selection,
                                          metrics = None,
                                          ):
    # Hyper-parameter via hyper_selection
    assert isinstance(hyper_selection, HyperSelection), "ERROR:kgcnn: Error require valid `HyperSelection`."

    # Dataset-information
    data_length = len(y_train)
    default_metric = "categorical_accuracy" if len(y_train.shape) > 1 and y_train.shape[-1] > 1 else "accuracy"
    default_loss = "categorical_crossentropy" if len(y_train.shape) > 1 and y_train.shape[-1] > 1 else "binary_crossentropy"

    # Make the model for current split.
    model = make_model(**hyper_selection.make_model())

    # Compile model with optimizer and loss
    model.compile(**hyper_selection.compile(loss=default_loss, metrics=[default_metric]))
    print(model.summary())

    # Start and time training
    start = time.process_time()
    hist = model.fit(X_train, y_train,
                     validation_data=validation_data,
                     **hyper_selection.fit()
                     )
    stop = time.process_time()
    print("Print Time for training: ",  str(timedelta(seconds=stop - start)))

    return model, hist


