import test from 'node:test';
import assert from 'node:assert/strict';
import { defaultBankChoice, invalidBankChoice } from '../src/bankImportChoices.ts';

test('bank movements default to reconciliation only, never automatic financial entries',()=>{
  const choice=defaultBankChoice('a'.repeat(64));
  assert.equal(choice.action,'BANK_ONLY');assert.equal(choice.cash_transaction_id,null);
  assert.equal(choice.classification_reviewed,false);
  assert.equal(invalidBankChoice(choice,'INCOME'),false);
});
test('link requires explicit choice of existing entry',()=>{
  const choice={...defaultBankChoice('a'.repeat(64)),action:'LINK'};
  assert.equal(invalidBankChoice(choice,'INCOME'),true);
  assert.equal(invalidBankChoice({...choice,cash_transaction_id:'selected-id'},'INCOME'),false);
});
test('incoming amounts cannot be converted into expenses',()=>{
  const choice={...defaultBankChoice('a'.repeat(64)),action:'EXPENSE'};
  assert.equal(invalidBankChoice(choice,'INCOME'),true);
  assert.equal(invalidBankChoice(choice,'EXPENSE'),false);
});
test('classified expenses need review and a nonempty category',()=>{
  const choice={...defaultBankChoice('a'.repeat(64)),action:'EXPENSE',expense_nature:'DIRECT_COST'};
  assert.equal(invalidBankChoice(choice,'EXPENSE'),true);
  assert.equal(invalidBankChoice({...choice,classification_reviewed:true},'EXPENSE'),false);
  assert.equal(invalidBankChoice({...choice,classification_reviewed:true,category:'   '},'EXPENSE'),true);
});
