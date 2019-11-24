import torch

import h5py
import random
import os
import numpy as np
import time
import datetime 

from dataload import mnist_load, cifar10_load
from model import SimpleCNN

import matplotlib.pyplot as plt

def seed_everything(seed=223):
    random.seed(seed)
    os.environ['PYTHONHASHSEED'] = str(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    torch.cuda.manual_seed(seed)
    torch.backends.cudnn.deterministic = True

class ModelTrain:
    def __init__(self, model, data, epochs, criterion, optimizer, device, model_name=None, savedir=None, monitor=None, mode=None, validation=None, verbose=0):
        '''
        params

        model: training model
        data: train dataset
        epochs: epochs
        criterion: critetion
        optimizer: optimizer
        device: [cuda:i, cpu], i=0, ...,n
        model_name: name of model to save
        savedir: directory to save
        monitor: metric name or loss to check [default: None]
        mode: [min, max] [default: None]
        validation: test set to evaluate in train [default: None]
        verbose: number of score print
        '''

        self.model = model
        self.train_set = data
        self.validation_set = validation
        self.criterion = criterion
        self.optimizer = optimizer
        self.device = device
        self.history = {}

        print('=====Train Mode======')
        ckp = CheckPoint(dirname=savedir,
                         model_name=model_name,
                         monitor=monitor,
                         mode=mode)
        # es = EarlyStopping(patience=20,
        #                    factor=0.01)

        # Training time check
        total_start = time.time()

        # Initialize history list
        train_acc_lst, train_loss_lst = [], []
        val_acc_lst, val_loss_lst = [], []
        epoch_time_lst = []

        for i in range(epochs):

            epoch_start = time.time()
            train_acc, train_loss = self.train()
            val_acc, val_loss = self.validation()        

            # Score check
            if i % verbose == 0:
                end = time.time()
                epoch_time = datetime.timedelta(seconds=end - epoch_start)
                print('\n[{0:}/{1:}] Train - Acc: {2:.4%}, Loss: {3:.5f} | Val - Acc: {4:.5%}, Loss: {5:.6f} | Time: {6:}\n'.format(i+1, epochs, train_acc, train_loss, val_acc, val_loss, epoch_time))

            # Model check
            if savedir:
                ckp.check(epoch=i+1, model=self.model, score=val_acc)
            # es.check(val_loss)

            # Save history
            train_acc_lst.append(train_acc)
            train_loss_lst.append(train_loss)

            val_acc_lst.append(val_acc)
            val_loss_lst.append(val_loss)

            epoch_time_lst.append(str(epoch_time))

            # if es.nb_patience == es.patience:
            #     break

        end = time.time() - total_start
        total_time = datetime.timedelta(seconds=end)
        print('\nFinish Train: Training Time: {}\n'.format(total_time))

        # Make history 
        self.history = {}
        self.history['train'] = []
        self.history['train'].append({
            'acc':train_acc_lst,
            'loss':train_loss_lst,
        })
        self.history['validation'] = []
        self.history['validation'].append({
            'acc':val_acc_lst,
            'loss':val_loss_lst,
        })
        self.history['time'] = []
        self.history['time'].append({
            'epoch':epoch_time_lst,
            'total':str(total_time)
        })

    def train(self):
        self.model.train()
        train_acc = 0
        train_loss = 0
        total_size = 0
        
        for inputs, targets in self.train_set:
            inputs, targets = inputs.to(self.device), targets.to(self.device)
            self.optimizer.zero_grad()

            outputs = self.model(inputs)
            loss = self.criterion(outputs, targets.long())
        
            # Update
            loss.backward()
            self.optimizer.step()

            # Loss
            train_loss += loss.item() / len(self.train_set)

            # Accuracy
            _, predicted = outputs.max(1)
            train_acc += predicted.eq(targets.long()).sum()
            total_size += targets.size(0)

        train_acc = train_acc.item() / total_size

        return train_acc, train_loss

    def validation(self):
        self.model.eval()
        val_acc = 0
        val_loss = 0
        total_size = 0

        with torch.no_grad():
            for inputs, targets in self.validation_set:
                inputs, targets = inputs.to(self.device), targets.to(self.device)

                outputs = self.model(inputs).detach() 

                # Loss
                loss = self.criterion(outputs, targets.long())
                val_loss += loss.item() / len(self.validation_set)

                # Accuracy
                _, predicted = outputs.max(1)
                val_acc += predicted.eq(targets.long()).sum()
                total_size += targets.size(0)
            
            val_acc = val_acc.item() / total_size
            
        return val_acc, val_loss



class ModelTest:
    def __init__(self, model, data, model_name, loaddir, device):
        '''
        params
        
        model: training model
        data: train dataset
        model_name: name of model to save
        loaddir: directory to load
        device: [cuda:i, cpu], i=0, ...,n
        '''

        self.model = model 
        self.test_set = data
        self.device = device

        load_file = torch.load(f'{loaddir}/{model_name}.pth')
        self.model.load_state_dict(load_file['model'])

        print('=====Test Mode======')
        print('Model load complete')
        del load_file['model']
        for k, v in load_file.items():
            print(f'{k}: {v}')

        start = time.time()
        self.results = self.test()
        end = time.time() - start
        test_time = datetime.timedelta(seconds=end)
        print('Test Acc: {0:.4%} | Time: {1:}'.format(self.results, test_time))

        

    def test(self):
        self.model.eval()
        test_acc = 0

        with torch.no_grad():
            for inputs, targets in self.test_set:
                inputs, targets = inputs.to(self.device), targets.to(self.device)

                outputs = self.model(inputs).detach() 
                # Accuracy
                _, predicted = outputs.max(1)
                test_acc += predicted.eq(targets).sum().item()
            
            test_acc = test_acc / len(self.test_set.dataset)

        return test_acc
        


class CheckPoint:
    def __init__(self, dirname, model_name, monitor, mode):
        '''
        params
        dirname: save directory
        model_name: model name
        monitor: metric name or loss
        mode: [min, max]
        '''

        self.best = 0
        self.model_name = model_name
        self.save_dir = dirname
        self.monitor = monitor
        self.mode = mode
        
        # if save directory is not there, make it
        if not(os.path.isdir(self.save_dir)):
            os.mkdir(self.save_dir)

    def check(self, epoch, model, score):
        '''
        params
        epoch: current epoch
        model: training model
        score: current score
        '''

        if self.mode == 'min':
            if score < self.best:
                self.model_save(epoch, model, score)
        elif self.mode == 'max':
            if score > self.best:
                self.model_save(epoch, model, score)

        
    def model_save(self, epoch, model, score):
        '''
        params
        epoch: current epoch
        model: training model
        score: current score
        '''

        print('Save complete, epoch: {0:}: Best {1:} has changed from {2:.5f} to {3:.5f}'.format(epoch, self.monitor, self.best, score))
        self.best = score
        state = {
            'model':model.state_dict(),
            f'best_{self.monitor}':score,
            'best_epoch':epoch
        }
        torch.save(state, f'{self.save_dir}/{self.model_name}.pth')



class EarlyStopping:
    def __init__(self, patience, factor=0.001):
        self.patience = patience
        self.factor = factor
        self.best_loss = 0
        self.nb_patience = 0

    def check(self, loss):
        if self.best_loss < loss + self.factor:
            # Initialize best loss
            if self.best_loss == 0:
                self.best_loss = loss
            else:
                self.nb_patience += 1
                print(f'Current patience is [{self.nb_patience}/{self.patience}]: ', end='')
                print('Best loss: {0:.5f} | Current loss + {1:}: {2:.5f}'.format(self.best_loss, self.factor, loss + self.factor))

        elif self.best_loss > loss:
            self.best_loss = loss


def get_samples(target, nb_class=10, sample_index=0):
    '''
    params:
        target : [mnist, cifar10]
        nb_class : number of classes
        example_index : index of image by class

    returns:
        original_images (numpy array) : Original images, shape = (number of class, W, H, C)
        pre_images (torch array) : Preprocessing images, shape = (number of class, C, W, H)
        target_classes (dictionary) : keys = class index, values = class name
        model (pytorch model) : pretrained model
    '''

    if target == 'mnist':
        image_size = (28,28,1)
        
        _, _, testloader = mnist_load()
        testset = testloader.dataset

    elif target == 'cifar10':
        image_size = (32,32,3)

        _, _, testloader = cifar10_load()
        testset = testloader.dataset

    # idx2class
    target_class2idx = testset.class_to_idx
    target_classes = dict(zip(list(target_class2idx.values()), list(target_class2idx.keys())))

    # select images
    idx_by_class = [np.where(np.array(testset.targets)==i)[0][sample_index] for i in range(nb_class)]
    original_images = testset.data[idx_by_class]
    if not isinstance(original_images, np.ndarray):
        original_images = original_images.numpy()
    original_images = original_images.reshape((nb_class,)+image_size)
    # select targets
    if isinstance(testset.targets, list):
        original_targets = torch.LongTensor(testset.targets)[idx_by_class]
    else:
        original_targets = testset.targets[idx_by_class]

    # model load
    weights = torch.load('../checkpoint/simple_cnn_{}.pth'.format(target))
    model = SimpleCNN(target)
    model.load_state_dict(weights['model'])

    # image preprocessing
    pre_images = torch.zeros(original_images.shape)
    pre_images = np.transpose(pre_images, (0,3,1,2))
    for i in range(len(original_images)):
        pre_images[i] = testset.transform(original_images[i])
    
    return original_images, original_targets, pre_images, target_classes, model


def rescale_image(images):
    '''
    MinMax scaling

    Args:
        images : images (batch_size, C, H, W)
    '''
    mins = np.min(images, axis=(1,2,3)) # (batch_size, 1)
    mins = mins.reshape(mins.shape + (1,1,1,)) # (batch_size, 1, 1, 1)
    maxs = np.max(images, axis=(1,2,3))
    maxs = maxs.reshape(maxs.shape + (1,1,1,))

    images = (images - mins)/(maxs - mins)
    images = images.transpose(0,2,3,1)

    return images


def visualize_saliencys(origin_imgs, results, probs, preds, classes, names, target, **kwargs):
    # initialize
    row = kwargs['row']
    col = kwargs['col']
    size = kwargs['size']
    fontsize = kwargs['fontsize']
    labelsize = kwargs['labelsize']
    
    if target=='mnist':
        origin_imgs= origin_imgs.squeeze()
        for i in range(len(results)):
            results[i] = results[i].squeeze()
        color = 'gray'
    else:
        color = None
            
    f, ax = plt.subplots(row, col, figsize=size)
    # original images
    for i in range(row):
        ax[i,0].imshow(origin_imgs[i], color)
        ax[i,0].set_ylabel('True: {0:}\nPred: {1:} ({2:.2%})'.format(classes[i], int(preds[i]), probs[i]), size=labelsize)
        ax[i,0].set_xticks([])
        ax[i,0].set_yticks([])
        # set title
        if i == 0:
            ax[i,0].set_title('Original Image', size=fontsize)

    for i in range(row*(col-1)):
        r = i//(col-1)
        c = i%(col-1)
        ax[r,c+1].imshow(results[c][r], color)
        ax[r,c+1].axis('off')
        # set title
        if r == 0:
            ax[r,c+1].set_title(names[c], size=fontsize)

    plt.subplots_adjust(wspace=-0.5, hspace=0)
    plt.tight_layout()


def visualize_selectivity(target, methods, steps, sample_pct, save_dir, **kwargs):
    # initialize
    kwargs['fontsize'] = 10 if 'fontsize' not in kwargs.keys() else kwargs['fontsize']
    kwargs['size'] = (5,5) if 'size' not in kwargs.keys() else kwargs['size']
    kwargs['color'] = ['b', 'g', 'r', 'c', 'm', 'y', 'k', 'w'] if 'color' not in kwargs.keys() else kwargs['color']
    kwargs['random_state'] = 223 if 'random_state' not in kwargs.keys() else kwargs['random_state']
    kwargs['dpi'] = None if 'dpi' not in kwargs.keys() else kwargs['dpi']

    # set results dictionary by attribution methods
    attr_method_dict = {}
    for i in range(len(methods)):    
        attr_method_dict[methods[i]] = {'data':[]}

    # results load
    for attr_method in attr_method_dict.keys():
        hf = h5py.File(f'../evaluation/{target}_{attr_method}_steps{steps}_ckp5_sample{sample_pct}.hdf5', 'r')
        attr_method_dict[attr_method]['data'] = hf

    # Accuracy Change by Methods
    f, ax = plt.subplots(1,len(methods)+1, figsize=kwargs['size'])
    for i in range(len(methods)):
        method = methods[i]
        # results load
        hf = h5py.File(f'../evaluation/{target}_{method}_steps{steps}_ckp5_sample{sample_pct}.hdf5', 'r')
        # acc
        acc = np.array(hf['acc'])
        # plotting
        ax[0].plot(range(steps+1), acc, label=method, color=kwargs['color'][i])
        ax[0].legend()
        # close
        hf.close()
    # text
    ax[0].set_xlabel('# pixel removed', size=kwargs['fontsize'])
    ax[0].set_ylabel('Accuracy', size=kwargs['fontsize'])
    ax[0].set_title('[{}] Accuracy Change\nby Methods'.format(target.upper()), size=kwargs['fontsize'])
    ax[0].set_ylim([0,1])

    # Score Change by Methods
    for i in range(len(methods)):
        method = methods[i]
        # results load
        hf = h5py.File(f'../evaluation/{target}_{method}_steps{steps}_ckp5_sample{sample_pct}.hdf5', 'r')
        # score
        score = np.array(hf['score'])
        mean_score = np.mean(score, axis=1)
        # plotting average score
        ax[i+1].plot(range(steps+1), mean_score, label=method, color=kwargs['color'][i], linewidth=4)
        # sample index
        np.random.seed(kwargs['random_state'])
        sample_idx = np.random.choice(score.shape[1], 100, replace=False)
        sample_score = score[:,sample_idx]
        # plotting
        for j in range(100):
            ax[i+1].plot(range(steps+1), sample_score[:,j], color=kwargs['color'][i], linewidth=0.1)
        # text
        ax[i+1].set_xlabel('# pixel removed', size=kwargs['fontsize'])
        ax[i+1].set_ylabel('Score for correct class', size=kwargs['fontsize'])
        ax[i+1].set_title('[{}] {}\nScore Change'.format(target.upper(), method), size=kwargs['fontsize'])
        ax[i+1].set_ylim([0,1])
        # close
        hf.close()

    # figure adjust
    plt.subplots_adjust(wspace=-0.5, hspace=0)
    plt.tight_layout()
    
    # save
    plt.savefig(save_dir,dpi=kwargs['dpi'])