import tensorflow as tf
from kgcnn.layers.casting import ChangeTensorType
from kgcnn.layers.conv.schnet_conv import SchNetInteraction
from kgcnn.layers.geom import NodeDistanceEuclidean, GaussBasisLayer, NodePosition
from kgcnn.layers.modules import DenseEmbedding, OptionalInputEmbedding
from kgcnn.layers.mlp import GraphMLP, MLP
from kgcnn.layers.pooling import PoolingNodes
from kgcnn.utils.models import update_model_kwargs
ks = tf.keras

# Implementation of Schnet in `tf.keras` from paper:
# by Kristof T. Schütt, Pieter-Jan Kindermans, Huziel E. Sauceda, Stefan Chmiela,
# Alexandre Tkatchenko, Klaus-Robert Müller (2018)
# https://doi.org/10.1063/1.5019779
# https://arxiv.org/abs/1706.08566  
# https://aip.scitation.org/doi/pdf/10.1063/1.5019779


model_default = {'name': "Schnet",
                 'inputs': [{'shape': (None,), 'name': "node_attributes", 'dtype': 'float32', 'ragged': True},
                            {'shape': (None, 3), 'name': "node_coordinates", 'dtype': 'float32', 'ragged': True},
                            {'shape': (None, 2), 'name': "edge_indices", 'dtype': 'int64', 'ragged': True}],
                 'input_embedding': {"node": {"input_dim": 95, "output_dim": 64}},
                 "make_distance": True, 'expand_distance': True,
                 'interaction_args': {"units": 128, "use_bias": True,
                                      "activation": 'kgcnn>shifted_softplus', "cfconv_pool": 'sum'},
                 'node_pooling_args': {"pooling_method": "sum"},
                 'depth': 4,
                 'gauss_args': {"bins": 20, "distance": 4, "offset": 0.0, "sigma": 0.4},
                 'verbose': 10,
                 'last_mlp': {"use_bias": [True, True], "units": [128, 64],
                              "activation": ['kgcnn>shifted_softplus', 'kgcnn>shifted_softplus']},
                 'output_embedding': 'graph',
                 "use_output_mlp": True,
                 'output_mlp': {"use_bias": [True, True], "units": [64, 1],
                                "activation": ['kgcnn>shifted_softplus', "linear"]}
                 }


@update_model_kwargs(model_default)
def make_model(inputs=None,
               input_embedding=None,
               make_distance=None,
               expand_distance=None,
               gauss_args=None,
               interaction_args=None,
               node_pooling_args=None,
               depth=None,
               name=None,
               verbose=None,
               last_mlp=None,
               output_embedding=None,
               use_output_mlp=None,
               output_mlp=None
               ):
    r"""Make `SchNet <https://arxiv.org/abs/1706.08566>`_ graph network via functional API.
    Default parameters can be found in :obj:`kgcnn.literature.Schnet.model_default`.

    Inputs:
        list: `[node_attributes, edge_distance, edge_indices]`
        or `[node_attributes, node_coordinates, edge_indices]` if :obj:`make_distance=True` and
        :obj:`expand_distance=True` to compute edge distances from node coordinates within the model.

            - node_attributes (tf.RaggedTensor): Node attributes of shape `(batch, None, F)` or `(batch, None)`
              using an embedding layer.
            - edge_distance (tf.RaggedTensor): Edge distance of shape `(batch, None, D)` expanded
              in a basis of dimension `D` or `(batch, None, 1)` if using a :obj:`GaussBasisLayer` layer
              with model argument :obj:`expand_distance=True` and the numeric distance between nodes.
            - edge_indices (tf.RaggedTensor): Index list for edges of shape `(batch, None, 2)`.
            - node_coordinates (tf.RaggedTensor): Node (atomic) coordinates of shape `(batch, None, 3)`.

    Outputs:
        tf.Tensor: Graph embeddings of shape `(batch, L)` if :obj:`output_embedding="graph"`.

    Args:
        inputs (list): List of dictionaries unpacked in :obj:`tf.keras.layers.Input`. Order must match model definition.
        input_embedding (dict): Dictionary of embedding arguments for nodes etc. unpacked in :obj:`Embedding` layers.
        make_distance (bool): Whether input is distance or coordinates at in place of edges.
        expand_distance (bool): If the edge input are actual edges or node coordinates instead that are expanded to
            form edges with a gauss distance basis given edge indices. Expansion uses `gauss_args`.
        gauss_args (dict): Dictionary of layer arguments unpacked in :obj:`GaussBasisLayer` layer.
        depth (int): Number of graph embedding units or depth of the network.
        interaction_args (dict): Dictionary of layer arguments unpacked in final :obj:`SchNetInteraction` layers.
        node_pooling_args (dict): Dictionary of layer arguments unpacked in :obj:`PoolingNodes` layers.
        verbose (int): Level of verbosity.
        name (str): Name of the model.
        last_mlp (dict): Dictionary of layer arguments unpacked in last :obj:`MLP` layer before output or pooling.
        output_embedding (str): Main embedding task for graph network. Either "node", "edge" or "graph".
        use_output_mlp (bool): Whether to use the final output MLP. Possibility to skip final MLP.
        output_mlp (dict): Dictionary of layer arguments unpacked in the final classification :obj:`MLP` layer block.
            Defines number of model outputs and activation.

    Returns:
        :obj:`tf.keras.models.Model`
    """
    # Make input
    node_input = ks.layers.Input(**inputs[0])
    xyz_input = ks.layers.Input(**inputs[1])
    edge_index_input = ks.layers.Input(**inputs[2])

    # embedding, if no feature dimension
    n = OptionalInputEmbedding(**input_embedding['node'],
                               use_embedding=len(inputs[0]['shape']) < 2)(node_input)
    edi = edge_index_input

    if make_distance:
        x = xyz_input
        pos1, pos2 = NodePosition()([x, edi])
        ed = NodeDistanceEuclidean()([pos1, pos2])
    else:
        ed = xyz_input

    if expand_distance:
        ed = GaussBasisLayer(**gauss_args)(ed)

    # Model
    n = DenseEmbedding(interaction_args["units"], activation='linear')(n)
    for i in range(0, depth):
        n = SchNetInteraction(**interaction_args)([n, ed, edi])

    n = GraphMLP(**last_mlp)(n)

    # Output embedding choice
    if output_embedding == 'graph':
        out = PoolingNodes(**node_pooling_args)(n)
        if use_output_mlp:
            out = MLP(**output_mlp)(out)
        main_output = out
    elif output_embedding == 'node':
        out = n
        if use_output_mlp:
            out = GraphMLP(**output_mlp)(out)
        # no ragged for distribution atm
        main_output = ChangeTensorType(input_tensor_type="ragged", output_tensor_type="tensor")(out)
    else:
        raise ValueError("Unsupported output embedding for mode `SchNet`")

    model = ks.models.Model(inputs=[node_input, xyz_input, edge_index_input], outputs=main_output)
    return model
