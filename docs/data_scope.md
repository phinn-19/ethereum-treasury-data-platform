# Data Scope

## Organization

ENS DAO

## Network

Ethereum Mainnet

## Primary monitored wallet

Name: ENS DAO Wallet / wallet.ensdao.eth

Address:
0xFe89cc7aBB2C4183683ab71653C4cdc9B02D44b7

This address is documented by ENS as one of the protocol-owned
on-chain accounts.

This project does not currently claim to represent the entire ENS treasury.
ENS also operates other addresses such as its Endowment and multisig wallets.

## Raw data scope

The raw ingestion layer collects all available records for the monitored wallet:

- normal Ethereum transactions
- ERC-20 token transfers
- internal ETH transactions

Raw ERC-20 data is not filtered by token.

## V1 analytics asset scope

Primary assets:

- ETH
- USDC
- ENS

Observed but not yet classified:

- USDCx

USDT is not currently included in the V1 analytics scope because it did not
appear in the recent ERC-20 profiling sample.

The asset scope may change if later historical data provides evidence that
additional assets are materially relevant.