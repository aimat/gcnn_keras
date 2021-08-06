import tensorflow as tf
from sklearn.model_selection import train_test_split
import matplotlib.pyplot as plt
import numpy as np
import time
from sklearn.preprocessing import StandardScaler
import kerastuner as kt
from tensorflow_addons.optimizers import AdamW

from kgcnn.literature.AttentiveFP import make_attentiveFP
from kgcnn.utils.data import ragged_tensor_from_nested_numpy
from kgcnn.utils.loss import ScaledMeanAbsoluteError, ScaledRootMeanSquaredError

from kgcnn.data.datasets.ESOL import ESOLDataset

dataset = ESOLDataset()
data_unit = "mol/L"
labels, nodes, edges, edge_indices, _ = dataset.get_graph()

# Train Test split
labels_train, labels_test, nodes_train, nodes_test, edges_train, edges_test, edge_indices_train, edge_indices_test = train_test_split(
    labels, nodes, edges, edge_indices,  train_size=0.9, random_state=1)

# Convert to tf.RaggedTensor or tf.tensor
# adj_matrix copy of the data is generated by ragged_tensor_from_nested_numpy()
nodes_train, edges_train, edge_indices_train = ragged_tensor_from_nested_numpy(
    nodes_train), ragged_tensor_from_nested_numpy(edges_train), ragged_tensor_from_nested_numpy(
    edge_indices_train)

nodes_test, edges_test, edge_indices_test = ragged_tensor_from_nested_numpy(
    nodes_test), ragged_tensor_from_nested_numpy(edges_test), ragged_tensor_from_nested_numpy(
    edge_indices_test)

# Scaling
scaler = StandardScaler(with_std=True, with_mean=True, copy=True)
labels_train = scaler.fit_transform(labels_train)
labels_test = scaler.transform(labels_test)

# Define Training Data
xtrain = nodes_train, edges_train, edge_indices_train
xtest = nodes_test, edges_test, edge_indices_test
ytrain = labels_train
ytest = labels_test


def build_model(hp):
    hp_depth = hp.Int('depth', min_value=1, max_value=5, step=1)
    hp_nnsize = hp.Int('nn_size', min_value=25, max_value=400, step=20)
    hp_lr_start = hp.Choice('lr_start', [1e-2, 5e-3, 1e-3, 5e-4, 1e-4])
    hp_dropout = hp.Choice('dropout', [0.0, 0.05, 0.1, 0.2])

    model = make_attentiveFP(
        input_node_shape=[None, 41],
        input_edge_shape=[None, 15],
        # Output
        output_embedding={"output_mode": 'graph'},
        output_mlp={"use_bias": [True, True], "units": [hp_nnsize, 1], "activation": ['kgcnn>leaky_relu', 'linear']},
        # model specs
        attention_args={"units": hp_nnsize},
        depth=hp_depth,
        dropout=hp_dropout
    )

    optimizer = tf.keras.optimizers.Adam(lr=hp_lr_start)

    mae_metric = ScaledMeanAbsoluteError((1, 1))
    rms_metric = ScaledRootMeanSquaredError((1, 1))
    if scaler.scale_ is not None:
        mae_metric.set_scale(np.expand_dims(scaler.scale_, axis=0))
        rms_metric.set_scale(np.expand_dims(scaler.scale_, axis=0))
    model.compile(loss='mean_squared_error',
                  optimizer=optimizer,
                  metrics=[mae_metric, rms_metric])

    return model

stop_early = tf.keras.callbacks.EarlyStopping(monitor='val_loss', patience=5)
tuner = kt.Hyperband(build_model,
                     objective='val_loss',
                     max_epochs=10, factor=3, directory="kt_test")

tuner.search(x=xtrain, y=ytrain, validation_data=(xtest, ytest),
             epochs=300)

best_hps = tuner.get_best_hyperparameters(num_trials=1)[0]
print("Best hyper-parameters", best_hps.values)

model = tuner.hypermodel.build(best_hps)
history = model.fit(x=xtrain, y=ytrain, validation_data=(xtest, ytest), epochs=300)

# Predict logD with model
pred_test = scaler.inverse_transform(model.predict(xtest))
true_test = scaler.inverse_transform(ytest)
mae_valid = np.mean(np.abs(pred_test - true_test))

# Predicted vs Actual
plt.figure()
plt.scatter(pred_test, true_test, alpha=0.3, label="MAE: {0:0.4f} ".format(mae_valid) + "[" + data_unit + "]")
plt.plot(np.arange(np.amin(true_test), np.amax(true_test), 0.05),
         np.arange(np.amin(true_test), np.amax(true_test), 0.05), color='red')
plt.xlabel('Predicted')
plt.ylabel('Actual')
plt.legend(loc='upper left', fontsize='x-large')
plt.savefig('attentiveFP_predict.png')
plt.show()