# This script performs two-step transfer learning.
# To run: 
# Step 1: python3 train.py ./config/[model_name].yaml
# Step 2: python3 train.py ./config/[model_name]_tune.yaml
import os
import csv
import random
import pickle
import argparse
import yaml
import sys
from datetime import datetime
import numpy as np
from sklearn.model_selection import train_test_split
import tensorflow as tf
from tensorflow.keras.preprocessing import image
import matplotlib.pyplot as plt

tf.random.set_seed(123)

# load images and their labels, normalize images and categorize labels
def preprocess_data(config, file_w_paths):

    not_found = []
    data = []
    labels = []
    # reading csv file 
    with open(file_w_paths, 'r') as csvfile:
        # create csv reader object 
        csv_reader = csv.reader(csvfile, delimiter = ",")
        # loading and processing each image one by one
        counter = 0
        for row in csv_reader:
            label = row[1].strip()  # get label 
            try:
                # load image
                img = image.load_img(path=row[0].strip(),
                        target_size=(config['DATASET']['img_size'], config['DATASET']['img_size'], 3),
                        grayscale=False)
                img = image.img_to_array(img)  # convert PIL image instance to Numpy array 
                img = img/255  # normalize the values to range from 0 to 1
                
                data.append(img)
                labels.append(label)
            
            except:
                not_found.append(row)
            ''' 
            counter += 1
            if counter == 100:
                break
            '''
    print('Images not found: ', not_found) 

    # convert list of integer labels to a binary matrix
    labels_cat = tf.keras.utils.to_categorical(labels, num_classes=config['DATASET']['num_class'])
    
    # pickle the data
    f = open(file_w_paths+'.pickle', 'wb')
    pickle.dump((data, labels_cat), f)
    f.close()

    return data, labels_cat

    
if __name__ == '__main__':

    parser = argparse.ArgumentParser()
    parser.add_argument('--config_path', type=str, required=True)
    parser.add_argument('--process_data', type=str, required=True, help='Does data need to be processed, "y" or "n"')
    args = parser.parse_args()
    config_path = args.config_path
    process_data = args.process_data

    # load config file
    with open(config_path) as file:
            config = yaml.safe_load(file)
    
    # load and process data, or just load if it has been previously processed and serialized
    if process_data == 'y':
        print('Loading and processing data from: ', config['DATASET']['data_path'])
        X_train, y_train = preprocess_data(config, config['DATASET']['train_path']) 
        X_val, y_val = preprocess_data(config, config['DATASET']['val_path'])
    elif process_data == 'n':
        print('Loading data from: ', config['DATASET']['data_path'])
        f = open(config['DATASET']['train_path']+'.pickle', 'rb')
        train_data = pickle.load(f)
        X_train = train_data[0]
        y_train = train_data[1]

        f = open(config['DATASET']['val_path']+'.pickle', 'rb')
        val_data = pickle.load(f)
        X_val = val_data[0]
        y_val = val_data[1]
    
    # convert to numpy array 
    X_train = np.array(X_train)
    y_train = np.array(y_train)
    X_val = np.array(X_val)
    y_val = np.array(y_val)
    print('X_train.shape:',X_train.shape,'y_train.shape:', y_train.shape)
    print('X_val.shape:', X_val.shape,'y_val.shape:', y_val.shape)
    
    # create data augmentation layer
    if config['TRAIN']['augment'] == True:
        data_augmentation = tf.keras.Sequential([
        # preprocessing layer which randomly flips images during training.
        #tf.keras.layers.RandomFlip('horizontal_and_vertical'),
        # preprocessing layer which randomly rotates images during training
        tf.keras.layers.RandomRotation(0.2)])
    
    # create base model or load pretrained model from step 1 to be tuned
    model_name = config['MODEL']['name'] 
    if model_name == 'resnet50':
        base_model = tf.keras.applications.ResNet50(include_top = False, weights='imagenet', 
                                            input_shape = (config['DATASET']['img_size'], 
                                                           config['DATASET']['img_size'],3))
    elif model_name == 'inceptionV3':
        base_model = tf.keras.applications.InceptionV3(include_top = False, weights='imagenet',
                                                            input_shape = (config['DATASET']['img_size'],
                                                            config['DATASET']['img_size'],3))
    
    elif model_name == 'inception_resnetV2':
        base_model = tf.keras.applications.InceptionResNetV2(include_top = False, weights='imagenet',
                                                            input_shape = (config['DATASET']['img_size'],
                                                            config['DATASET']['img_size'],3))
    elif model_name == 'xception':
        base_model = tf.keras.applications.xception.Xception(include_top = False, weights='imagenet',
                                                            input_shape = (config['DATASET']['img_size'],
                                                            config['DATASET']['img_size'],3))
    elif model_name == 'vgg16':
        base_model = tf.keras.applications.VGG16(include_top=False, weights="imagenet",
                                                  input_shape=(config['DATASET']['img_size'],
                                                            config['DATASET']['img_size'],3)) 
    elif model_name == 'efficientnetB0':
        base_model = tf.keras.applications.EfficientNetB0(include_top=False, weights="imagenet",
                                                        input_shape=(config['DATASET']['img_size'],
                                                             config['DATASET']['img_size'],3))
    # if 2nd step of two-step transfer learning process
    else:
        model = tf.keras.models.load_model(config['MODEL']['tune_path'])
    

    # freeze layers of base_model (step 1) or make layers trainable for tuning (step 2) 
    if config['TRAIN']['tune'] == False:
        base_model.trainable = False
        for i, layer in enumerate(base_model.layers):
            #print(i, layer.name,"-", layer.trainable)
    else:
        for layer in model.layers:
            layer.trainable = True
        for i, layer in enumerate(model.layers):
            print(i, layer.name,"-", layer.trainable)

    
    # define model architecture if step 1
    if config['TRAIN']['tune'] == False:
        inp = tf.keras.Input((config['DATASET']['img_size'], config['DATASET']['img_size'], 3))
        if config['TRAIN']['augment'] == True:
            x = data_augmentation(inp)
            x = base_model(x, training=False)
        else:
            x = base_model(inp, training=False)
        x = tf.keras.layers.GlobalAveragePooling2D()(x)
        #x = tf.keras.layers.Dense(256, activation='relu')(x)
        x = tf.keras.layers.Dropout(0.3)(x)
        x = tf.keras.layers.Dense(128, activation='relu')(x)
        x = tf.keras.layers.Dense(64, activation='relu')(x)
        out = tf.keras.layers.Dense(config['DATASET']['num_class'], activation='softmax')(x)
        model = tf.keras.Model(inp, out)
        
        # compile the model
        if config['TRAIN']['optimizer'] == "SGD":
            model.compile(optimizer=tf.keras.optimizers.SGD(learning_rate=0.02, momentum=0.9,
                    weight_decay=0.0001),
                    loss='categorical_crossentropy',
                    metrics=['accuracy'])
        else:
            model.compile(optimizer=tf.keras.optimizers.Adam(learning_rate=config['TRAIN']['lr']),
                    loss='categorical_crossentropy',
                    metrics=['accuracy']) 
    
    print(model.summary())
        
    # create checkpoint and early stopping 
    checkpoint = tf.keras.callbacks.ModelCheckpoint(
                filepath='checkpoints/' + model_name + '_{epoch:03d}-{accuracy:.3f}-{val_accuracy:.3f}.h5',
                monitor='val_accuracy',
                verbose=1,
                save_best_only=True,
                save_weights_only=True,
                save_freq='epoch')  

    early_stop = tf.keras.callbacks.EarlyStopping(
                monitor='val_loss', 
                patience=10,
                mode='min', 
                verbose=1) 
    
    
    # train model
    print('Training ',  config['MODEL']['name'])
    batch_size = config['TRAIN']['batch_size']
    num_epoch = config['TRAIN']['num_epoch']
    train_steps = X_train.shape[0] // batch_size
    val_steps = X_val.shape[0] // batch_size
    
    #print("Num GPUs Available: ", len(tf.config.list_physical_devices('GPU')))
    print('num_epochs:', num_epoch, 'batch_size:', batch_size, 'train_steps:', train_steps, 
            'val_steps:', val_steps)

    # fit model
    history = model.fit(X_train,
                        y_train,
                        steps_per_epoch=train_steps,
                        validation_data=(X_val, y_val),
                        validation_steps=val_steps,
                        batch_size=batch_size,
                        epochs=num_epoch,
                        callbacks=[checkpoint, early_stop],
                        verbose=1) 
   
    # save model
    print('Saving to ', config['MODEL']['model_path'])
    model.save(filepath=config['MODEL']['model_path'], save_format="h5")
    
    
    # model performance 
    acc = history.history['accuracy']
    val_acc = history.history['val_accuracy']
    loss = history.history['loss']
    val_loss = history.history['val_loss']

    # plot: train/val accuracy 
    plt.figure(figsize=(10, 16))
    plt.rcParams['figure.figsize'] = [16, 9]
    plt.rcParams['font.size'] = 14
    plt.rcParams['axes.grid'] = True
    plt.rcParams['figure.facecolor'] = 'white'
    plt.subplot(2, 1, 1)
    plt.plot(acc, label='Training Accuracy')
    plt.plot(val_acc, label='Validation Accuracy')
    plt.legend(loc='lower right')
    plt.ylabel('Accuracy')
    plt.title(f'Training and Validation Accuracy')
    plt.savefig(config['MODEL']['plots_path']+config['MODEL']['name']+'_acc')
 
    # plot: train/val loss
    plt.figure(figsize=(10, 16))
    plt.plot(loss, label='Training Loss')
    plt.plot(val_loss, label='Validation Loss')
    plt.legend(loc='upper right')
    plt.ylabel('Cross Entropy')
    plt.title(f'Training and Validation Loss')
    plt.xlabel('epoch')
    plt.tight_layout(pad=3.0)
    plt.savefig(config['MODEL']['plots_path']+config['MODEL']['name']+'_loss')


