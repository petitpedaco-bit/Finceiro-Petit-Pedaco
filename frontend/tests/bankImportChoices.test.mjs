import test from 'node:test';
import assert from 'node:assert/strict';
import { defaultBankChoice, invalidBankChoice } from '../src/bankImportChoices.ts';
import { bankHistoryQuery, emptyBankFilters } from '../src/bankHistoryFilters.ts';
import { readFileSync } from 'node:fs';

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
test('revenue requires an incoming movement and a nonempty category',()=>{
  const choice={...defaultBankChoice('a'.repeat(64)),action:'INCOME',category:'Outras receitas'};
  assert.equal(invalidBankChoice(choice,'INCOME'),false);
  assert.equal(invalidBankChoice(choice,'EXPENSE'),true);
  assert.equal(invalidBankChoice({...choice,category:' '},'INCOME'),true);
});
test('history filters retain pagination and safely encode description searches',()=>{
  const filters={...emptyBankFilters(),start_date:'2026-10-12',end_date:'2026-10-13',direction:'EXPENSE',treatment:'BANK_ONLY',search:' João & 100% '};
  const params=new URLSearchParams(bankHistoryQuery(20,filters));
  assert.equal(params.get('offset'),'20');assert.equal(params.get('limit'),'20');
  assert.equal(params.get('search'),'João & 100%');assert.equal(params.get('direction'),'EXPENSE');
  assert.equal(params.get('start_date'),'2026-10-12');assert.equal(params.get('treatment'),'BANK_ONLY');
  const cleared=new URLSearchParams(bankHistoryQuery(0,emptyBankFilters()));
  assert.equal([...cleared.keys()].length,2);assert.equal(cleared.get('offset'),'0');
});
test('sale confirmation is guarded and report cancellation refreshes financial totals',()=>{
  const app=readFileSync(new URL('../src/App.tsx',import.meta.url),'utf8');
  const panel=readFileSync(new URL('../src/SalesHistoryPanel.tsx',import.meta.url),'utf8');
  const api=readFileSync(new URL('../src/api.ts',import.meta.url),'utf8');
  const checkout=readFileSync(new URL('../src/SaleCheckout.tsx',import.meta.url),'utf8');
  assert.ok(checkout.includes('if(checkoutLock.current)return'));
  assert.ok(checkout.includes('disabled={submitting} className="pos sale-guard"'));
  assert.ok(app.includes('<SalesHistoryPanel refresh={refresh}/>'));
  assert.ok(panel.includes('await load();await refresh();'));
  assert.ok(api.includes("cache:'no-store'"));
});
