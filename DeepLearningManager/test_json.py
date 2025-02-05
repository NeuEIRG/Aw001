import json
import tensorflow as tf
import numpy as np
import time
import os
import sys
import random
import pickle

def data_preprocessing(x_train,x_test):

    x_train = x_train.astype('float32')
    x_test = x_test.astype('float32')

    x_train[:, :, :, 0] = (x_train[:, :, :, 0] - np.mean(x_train[:, :, :, 0])) / np.std(x_train[:, :, :, 0])
    x_train[:, :, :, 1] = (x_train[:, :, :, 1] - np.mean(x_train[:, :, :, 1])) / np.std(x_train[:, :, :, 1])
    x_train[:, :, :, 2] = (x_train[:, :, :, 2] - np.mean(x_train[:, :, :, 2])) / np.std(x_train[:, :, :, 2])

    x_test[:, :, :, 0] = (x_test[:, :, :, 0] - np.mean(x_test[:, :, :, 0])) / np.std(x_test[:, :, :, 0])
    x_test[:, :, :, 1] = (x_test[:, :, :, 1] - np.mean(x_test[:, :, :, 1])) / np.std(x_test[:, :, :, 1])
    x_test[:, :, :, 2] = (x_test[:, :, :, 2] - np.mean(x_test[:, :, :, 2])) / np.std(x_test[:, :, :, 2])

    return x_train, x_test

def unpickle(file):
    with open(file, 'rb') as fo:
        dict = pickle.load(fo,encoding='bytes')
    return dict


def load_data_one(file):
    batch = unpickle(file)
    data = batch[b'data']
    labels = batch[b'labels']
    return data, labels


def load_data(files, data_dir, label_count,meta):
    global image_size, img_channels
    data, labels = load_data_one(data_dir + '/' + files[0])
    for f in files[1:]:
        data_n, labels_n = load_data_one(data_dir + '/' + f)
        data = np.append(data, data_n, axis=0)
        labels = np.append(labels, labels_n, axis=0)
    labels = np.array([[float(i == label) for i in range(label_count)] for label in labels])
    data = data.reshape([-1,meta['image_channel'], meta['image_height'],meta['image_width']])
    data = data.transpose([0, 2, 3, 1])
    return data, labels


def prepare_data(data_dir,json_meta):
    image_dim = json_meta['image_height'] * json_meta['image_width'] * json_meta['image_channel']
    meta = unpickle(data_dir + '/batches.meta')

    label_names = meta[b'label_names']
    label_count = len(label_names)
    train_files = ['data_batch_%d' % d for d in range(1, 6)]
    train_data, train_labels = load_data(train_files, data_dir, label_count,json_meta)
    test_data, test_labels = load_data(['test_batch'], data_dir, label_count,json_meta)

    indices = np.random.permutation(len(train_data))
    train_data = train_data[indices]
    train_labels = train_labels[indices]

    train_data,test_data = data_preprocessing(train_data,test_data)

    return train_data, train_labels, test_data, test_labels



train_flag = tf.placeholder(tf.bool)
keep_prob = tf.placeholder(tf.float32)
learning_rate = tf.placeholder(tf.float32)


def ParseInput(meta):
	return tf.placeholder(tf.float32,[None, meta['image_height'], meta['image_width'], meta['image_channel']])

def ParseConvolution(layer,net):
    W = tf.get_variable(layer['name'],shape=layer['weight_shape'], initializer=tf.contrib.keras.initializers.he_normal())
    b = tf.Variable(tf.constant(0.1, shape=layer['bias_shape'], dtype=tf.float32))
    return tf.nn.conv2d(net, W, strides=layer['strides'], padding=layer['padding']) + b

def ParseBatchNorm(layer,net):
    return tf.contrib.layers.batch_norm(net, decay=0.9, center=True, scale=True, epsilon=1e-3,
                                        is_training=train_flag, updates_collections=None)

def ParseRelu(layer,net):
	return tf.nn.relu(net)


def ParseFC(layer,net):
	net = tf.contrib.layers.flatten(net)
	W = tf.get_variable(layer['name'], shape=layer['weight_shape'], initializer=tf.contrib.keras.initializers.he_normal())
	b = tf.Variable(tf.constant(0.1, shape=layer['bias_shape'], dtype=tf.float32))
	return tf.matmul(net, W) + b 


def ParsePooling(layer,net):
	if layer['pooling_type']=='avg':
		return tf.nn.avg_pool(net, ksize=layer['ksize'], strides=layer['strides'],padding=layer['padding'], name=layer['name'])
	elif layer['pooling_type']=='max':	
		return tf.nn.max_pool(net, ksize=layer['ksize'], strides=layer['strides'],padding=layer['padding'], name=layer['name'])

def ParseLabel(meta):
	return tf.placeholder(tf.float32, [None, meta['num_classes']])


def ParseNetwork(json_obj):
	layers = json_obj["layer"]
	input_x = ParseInput(json_obj['meta'])
	input_y = ParseLabel(json_obj['meta'])
	net = input_x
	for layer in layers:
		layer_type = layer['type']
		if layer_type=='ConvolutionLayer':
			net = ParseConvolution(layer,net)
		elif layer_type=='BatchNormLayer':
			net = ParseBatchNorm(layer,net)
		elif layer_type=='ReluLayer':
			net = ParseRelu(layer,net)
		elif layer_type=='FCLayer':
			net = ParseFC(layer,net)
		elif layer_type=='PoolingLayer':
			net = ParsePooling(layer,net)

		print(layer_type)
	return net,input_x,input_y



def ParseLoss(json_obj,net,labels):
	meta = json_obj['meta']
	cross_entropy = tf.reduce_mean(tf.nn.softmax_cross_entropy_with_logits(labels=labels,logits=net))
	return cross_entropy


def ParseTrainStep(json_obj,cross_entropy):
	meta = json_obj['meta']
	learning_rate = meta['learning_rate']
	momentum_rate = meta['momentum_rate']
	l2 = tf.add_n([tf.nn.l2_loss(var) for var in tf.trainable_variables()])
	loss = cross_entropy + l2*meta['weight_decay']
	return tf.train.MomentumOptimizer(learning_rate, momentum_rate, use_nesterov=True).minimize(loss)


def ParseAccuracy(json_obj,net,labels):
	meta = json_obj['meta']
	correct_prediction = tf.equal(tf.argmax(net, 1), tf.argmax(labels, 1))
	return tf.reduce_mean(tf.cast(correct_prediction, tf.float32))


def learning_rate_schedule(epoch_num):
    if epoch_num < 81:
        return 0.1
    elif epoch_num < 121:
        return 0.01
    else:
        return 0.001


def run_testing(sess,test_x,test_y,loss,accuracy):
    acc = 0.0
    loss = 0.0
    pre_index = 0
    add = 1000
    for it in range(10):
        batch_x = test_x[pre_index:pre_index+add]
        batch_y = test_y[pre_index:pre_index+add]
        pre_index = pre_index + add
        loss_, acc_  = sess.run([cross_entropy, accuracy],
                                feed_dict={x: batch_x, y_: batch_y, keep_prob: 1.0, train_flag: False})
        loss += loss_ / 10.0
        acc += acc_ / 10.0
    return acc, loss



if __name__ == '__main__':

	json_file_url = "./test.json"
	image_data_url = "./cifar-10-batches-py"
	model_save_path = "./model"
	total_epoch = 164
	dropout_rate = 0.5
	iterations = 200
	batch_size = 250

	with open(json_file_url,"r") as json_file:
		json_obj = json.load(json_file)

	net,x,y_ = ParseNetwork(json_obj)
	loss = ParseLoss(json_obj,net,y_)
	train_step = ParseTrainStep(json_obj,loss)
	accuracy = ParseAccuracy(json_obj,net,y_)

	train_x, train_y, test_x, test_y = prepare_data(image_data_url,json_obj['meta'])

	saver = tf.train.Saver()

	with tf.Session() as sess:

	    sess.run(tf.global_variables_initializer())

	    for ep in range(1, total_epoch+1):
	        lr = learning_rate_schedule(ep)
	        pre_index = 0
	        train_acc = 0.0
	        train_loss = 0.0

	        for it in range(1, iterations+1):
	            batch_x = train_x[pre_index:pre_index+batch_size]
	            batch_y = train_y[pre_index:pre_index+batch_size]

	            _, batch_loss = sess.run([train_step, loss],
	                                     feed_dict={x: batch_x, y_: batch_y, keep_prob: dropout_rate,
	                                                learning_rate: lr, train_flag: True})
	            batch_acc = accuracy.eval(feed_dict={x: batch_x, y_: batch_y, keep_prob: 1.0, train_flag: True})

	            train_loss += batch_loss
	            train_acc += batch_acc
	            pre_index += batch_size

	            if it == iterations:
	                train_loss /= iterations
	                train_acc /= iterations

	                val_acc, val_loss = run_testing(sess,test_x,test_y,loss,accuracy)

	    save_path = saver.save(sess, model_save_path)
