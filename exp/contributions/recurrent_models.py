import torch
import torch.nn                         as nn
from   torch.nn                         import Parameter
from   torch.nn                         import functional as F
import torch.optim
from   torch                            import autograd
from   torch.autograd                   import Variable
from   core_qnn.quaternion_layers       import QuaternionLinearAutograd

class StackedQLSTM(nn.Module):
    def __init__(self, feat_size, hidden_size, use_cuda, n_layers, batch_first=True):
        super(StackedQLSTM, self).__init__()
        self.batch_first = batch_first
        self.layers = nn.ModuleList([QLSTM(feat_size, hidden_size, use_cuda) for _ in range(n_layers)])

    def forward(self, x):
        # QLSTM takes inputs of shape (seq_len, batch_size, feat_size)
        if self.batch_first:
            x = x.permute(1,0,2)
        for layer in self.layers:
            x = layer(x)
            # Remove extra feature added by QLSTM
            x = x[:,:,:-1]
        if self.batch_first:
            x = x.permute(1,0,2)
        return x

class QLSTM(nn.Module):
    def __init__(self, feat_size, hidden_size, CUDA):
        super(QLSTM, self).__init__()

        # Reading options:
        self.act=nn.Tanh()
        self.act_gate=nn.Sigmoid()
        self.input_dim=feat_size
        self.hidden_dim=hidden_size
        self.CUDA=CUDA

        # +1 because feat_size = the number on the sequence, and the output one hot will also have
        # a blank dimension so FEAT_SIZE + 1 BLANK
        self.num_classes=feat_size + 1

        # Gates initialization
        self.wfx  = QuaternionLinearAutograd(self.input_dim, self.hidden_dim) # Forget
        self.ufh  = QuaternionLinearAutograd(self.hidden_dim, self.hidden_dim, bias=False) # Forget

        self.wix  = QuaternionLinearAutograd(self.input_dim, self.hidden_dim) # Input
        self.uih  = QuaternionLinearAutograd(self.hidden_dim, self.hidden_dim, bias=False) # Input

        self.wox  = QuaternionLinearAutograd(self.input_dim, self.hidden_dim) # Output
        self.uoh  = QuaternionLinearAutograd(self.hidden_dim, self.hidden_dim, bias=False) # Output

        self.wcx  = QuaternionLinearAutograd(self.input_dim, self.hidden_dim) # Cell
        self.uch  = QuaternionLinearAutograd(self.hidden_dim, self.hidden_dim, bias=False) # Cell

        # Output layer initialization
        self.fco = nn.Linear(self.hidden_dim, self.num_classes)

        # Optimizer
        self.adam = torch.optim.Adam(self.parameters(), lr=0.005)


    def forward(self, x):

        h_init = Variable(torch.zeros(x.shape[1],self. hidden_dim))
        if self.CUDA:
            x=x.cuda()
            h_init=h_init.cuda()
        # Feed-forward affine transformation (done in parallel)
        wfx_out=self.wfx(x)
        wix_out=self.wix(x)
        wox_out=self.wox(x)
        wcx_out=self.wcx(x)

        # Processing time steps
        out = []

        c=h_init
        h=h_init

        for k in range(x.shape[0]):

            ft=self.act_gate(wfx_out[k]+self.ufh(h))
            it=self.act_gate(wix_out[k]+self.uih(h))
            ot=self.act_gate(wox_out[k]+self.uoh(h))

            at=wcx_out[k]+self.uch(h)
            c=it*self.act(at)+ft*c
            h=ot*self.act(c)

            output = self.fco(h)
            out.append(output.unsqueeze(0))

        return torch.cat(out,0)
