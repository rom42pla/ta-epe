from einops.layers.torch import Rearrange
from typing import List
from torch import nn
import torch

class ViT(nn.Module):
    def __init__(self,
                 in_channels: int,
                 labels: List[str],
                 labels_classes: int,
                 dropout_p: float,
                 mels: int,
                 hidden_size: int,
                 num_heads: int,
                 num_encoders: int,
                 num_decoders: int,
                 use_encoder_only: bool,
                 device: any,
                 positional_encoding: nn.Module = None,
                 use_learnable_token: bool = True
                ):
        super().__init__()
        
        # TO DO: Check parameters validity
        self.in_channels = in_channels
        self.labels = labels
        self.labels_classes = labels_classes
        self.dropout_p = dropout_p
        self.mels = mels
        self.hidden_size = hidden_size
        self.num_heads = num_heads
        self.num_encoders = num_encoders
        self.num_decoders = num_decoders
        self.use_encoder_only = use_encoder_only
        self.positional_encoding = positional_encoding
        self.use_learnable_token = use_learnable_token
        self.device = device
        
        self.dropout = nn.Dropout(p=self.dropout_p) # Dropout layer

        self.encoder = nn.TransformerEncoder(
            encoder_layer=nn.TransformerEncoderLayer(
                batch_first=True,
                d_model=self.hidden_size,
                dim_feedforward=self.hidden_size * 4,
                dropout=self.dropout_p,
                activation=nn.functional.relu,
                nhead=self.num_heads,
            ),
            num_layers=self.num_encoders,
        )

        if not self.use_encoder_only:
            self.labels_embedding = nn.Embedding(len(self.labels), self.hidden_size)
            self.decoder = nn.TransformerDecoder(
                decoder_layer=nn.TransformerDecoderLayer(
                    batch_first=True,
                    d_model=self.hidden_size,
                    dim_feedforward=self.hidden_size * 4,
                    dropout=self.dropout_p,
                    activation=nn.functional.relu,
                    nhead=self.num_heads,
                ),
                num_layers=self.num_decoders,
            )

        if self.use_learnable_token:
            self.cls = nn.Embedding(1, self.hidden_size)

        # Prepare the data for the transformer by merging the mel bands
        self.merge_mels = nn.Sequential(
            nn.Conv2d(
                in_channels=self.in_channels,
                out_channels=self.hidden_size,
                kernel_size=(self.mels, 1), # TO DO: Try to modify the kernel size to see if it improves the model
                stride=1,
                padding=0,
            ),
            Rearrange("b c m s -> b s (c m)")
        )

        # Add the classifier
        self.fc_layers = []
        self.fc_layers.append(self.dropout)
        self.fc_layers.append(nn.Linear(self.hidden_size, len(self.labels)))
        
        self.classifier = nn.Sequential(*self.fc_layers)
        
    def forward(self, x):
        if not self.use_encoder_only:
            label_tokens = self.labels_embedding.weight.expand(x.size(0), -1, -1)  # Expand label tokens to the batch size
        #print(x.shape)
        x = self.merge_mels(x) # Merge the mel bands (b c s m -> b s (c m))
        #print(x.shape)
        if self.positional_encoding is not None:
            x = self.positional_encoding(x) # Add positional encoding
            if not self.use_encoder_only:
                label_tokens = self.positional_encoding(label_tokens) # Add positional encoding to the label tokens
        #print(self.cls.weight.shape)
        if self.use_learnable_token:
            cls_token = self.cls.weight.expand(x.size(0), -1, -1)  # Expand cls token to the batch size
            x = torch.cat([cls_token, x], dim=1)  # Add learnable token
        print(x.shape)
        x = self.encoder(x)
        print(x.shape)
        if self.use_encoder_only:
            x = x[:, 0, :]
        else:
            x = self.decoder(label_tokens, x)[:, 0, :]
        print(x.shape)
        x = self.classifier(x)
        print(x.shape)
        return x