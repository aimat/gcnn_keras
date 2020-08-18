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
from kgcnn.literature.Megnet import getmodelMegnet


# Download Dataset
qm7b_download_dataset("")

# Read dataset
qm7b = QM7bFile("qm7b.mat")
y_data = qm7b.ylabels[:,8] + 7.0 # HOMO + some offset
x_data = [qm7b.proton, 
          [np.expand_dims(x,axis=-1) for x in qm7b.bonds_invdist],
          qm7b.bond_index, 
          np.expand_dims(qm7b.numatoms,axis=-1)/24.0]  # node, edgetype, edgeindex, state

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
    out = [tf.ragged.constant(inlist[0]),
           tf.ragged.constant(inlist[1],ragged_rank=1,inner_shape=(1,)),
           tf.ragged.constant(inlist[2],ragged_rank=1,inner_shape=(2,)),
           tf.constant(inlist[3])
           ]
    return out
xtrain = to_ragged(xtrain) 
xval = to_ragged(xval) 


model =  getmodelMegnet(  
                input_type = "raggged",
                nfeat_edge = 1,
                nfeat_global = 1,
                nfeat_node = None,
                nblocks = 3,
                n1 = 64,
                n2 = 32,
                n3 = 16,
                set2set_dim = 16,
                nvocal = 18,
                embedding_dim = 16,
                nbvocal= None,
                bond_embedding_dim = None,
                ngvocal = 24,
                global_embedding_dim = 16,
                ntarget = 1,
                use_bias = True,
                #act = softplus2,
                l2_coef = None,
                has_ff  = True,
                dropout = None,
                dropout_on_predict = False,
                is_classification = False,
                use_set2set = True,
                npass = 3,
                set2set_init = 'mean',
                set2set_pool = "mean"
                )

learning_rate = 1e-3
epo = 400
epostep = 10

def get_lr_metric(optimizer):
    def lr(y_true, y_pred):
        return optimizer.lr
    return lr
optimizer = tf.keras.optimizers.Adam(lr=learning_rate)
lr_metric = get_lr_metric(optimizer)
cbks = tf.keras.callbacks.LearningRateScheduler(lambda epoch: learning_rate - 0.5*learning_rate/epo*epoch)
model.compile(loss='mean_squared_error',
              optimizer=optimizer,
              metrics=['mean_absolute_error', 'mean_squared_error',lr_metric])

print(model.summary())

trainlossall = []
testlossall = []
validlossall = []

start = time.process_time()
for iepoch in range(0,epo,epostep):

    hist = model.fit(xtrain, ytrain, 
              epochs=iepoch+epostep,
              initial_epoch=iepoch,
              batch_size=48,
              callbacks=[cbks]
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