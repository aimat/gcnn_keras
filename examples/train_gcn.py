"""Example learning
"""
import time
import numpy as np
import tensorflow as tf
import tensorflow.keras as ks
import matplotlib.pyplot as plt
from sklearn.model_selection import train_test_split

from kgcnn.data.qm.setupQM import qm7b_download_dataset
from kgcnn.data.qm.QMFile import QM7bFile
from kgcnn.literature.GCN import getmodelGCN,precompute_adjacency_scaled,scaled_adjacency_to_list



# Download Dataset
qm7b_download_dataset("")

# Read dataset
qm7b = QM7bFile("qm7b.mat")
y_data = qm7b.ylabels[:,9] + 2.0 # LUMO + some offset
A_data = [scaled_adjacency_to_list(x,precompute_adjacency_scaled(x)) for x in qm7b.adjacency ] # simply all connected
x_data = [[np.expand_dims(x,axis=-1) for x in qm7b.proton],
          [x[0] for x in A_data],
          [np.expand_dims(x[1],axis=-1) for x in A_data]]  # node, edgetype, edgeindex, state

#Make test/train split
from sklearn.utils import shuffle
inds = np.arange(len(y_data))
inds = shuffle(inds)
ind_val = inds[:700]
ind_train = inds[700:]

# Select train/test data
xtrain = [[x[i] for i in ind_train] for x in x_data]
ytrain = y_data[ind_train]
xval = [[x[i] for i in ind_val] for x in x_data]
yval = y_data[ind_val]

#Make ragged tensor
def to_ragged(inlist):
    out = [tf.ragged.constant(inlist[0],ragged_rank=1,inner_shape=(1,)),
           tf.ragged.constant(inlist[1],ragged_rank=1,inner_shape=(2,)),
           tf.ragged.constant(inlist[2],ragged_rank=1,inner_shape=(1,))
           ]
    return out
xtrain = to_ragged(xtrain) 
xval = to_ragged(xval) 

model = getmodelGCN(
            input_nodedim = 1,
            input_type = "ragged",
            depth = 3,
            node_dim = [50,50,50],
            output_dim = [25,10,1],
            use_bias = True,
            activation = 'relu',
            use_pooling = True,
            output_activ = "linear"
            )

learning_rate = 1e-3
optimizer = tf.keras.optimizers.Adam(lr=learning_rate)
model.compile(loss='mean_squared_error',
              optimizer=optimizer,
              metrics=['mean_absolute_error', 'mean_squared_error'])
print(model.summary())

trainlossall = []
testlossall = []
validlossall = []
epo = 2000
epostep = 10

start = time.process_time()
for iepoch in range(0,epo,epostep):

    hist = model.fit(xtrain, ytrain, 
              epochs=iepoch+epostep,
              initial_epoch=iepoch,
              batch_size=48
              )

    trainlossall.append(hist.history['mean_absolute_error'][-1])
    testlossall.append(model.evaluate(xval, yval)[1])    

stop = time.process_time()
print("Print Time for taining: ",stop - start)

trainlossall =np.array(trainlossall)
testlossall = np.array(testlossall)

#Plot loss vs epochs    
plt.figure()
plt.plot(np.arange(epostep,epo+epostep,epostep),trainlossall,label='Training Loss')
plt.plot(np.arange(epostep,epo+epostep,epostep),testlossall,label='Test Loss')
plt.xlabel('Epochs')
plt.ylabel('Loss MAE eV')
plt.legend(loc='upper right',fontsize='x-large')


#Predicted vs Actual    
preds = model.predict(xval)
plt.figure()
plt.scatter(preds, yval, alpha=0.3)
plt.plot(np.arange(np.amin(yval), np.amax(yval),0.05), np.arange(np.amin(yval), np.amax(yval),0.05), color='red')
plt.xlabel('Predicted')
plt.ylabel('Actual')