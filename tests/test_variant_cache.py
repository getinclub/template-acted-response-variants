import copy
import itertools
import unittest
from variant_cache import capture_entry as capture, select_variant as select

def entry(**kw):
    args = dict(vary='Accept-Language', stored_at=10, max_age=20)
    args.update(kw)
    return capture('GET','/help',{'Accept-Language':'fr'},'Bonjour',**args)

class Variants(unittest.TestCase):
    def test_language_mismatch(self): self.assertIsNone(select([entry()],'GET','/help',{'accept-language':'en'},11))
    def test_header_name_case(self): self.assertEqual(select([entry()],'GET','/help',{'ACCEPT-LANGUAGE':'fr'},11)['body'],'Bonjour')
    def test_value_case_matters(self): self.assertIsNone(select([entry()],'GET','/help',{'Accept-Language':'FR'},11))
    def test_missing_empty_distinct(self):
        for a,b in [({}, {'X':''}),({'X':''},{})]:
            with self.subTest(a=a): self.assertIsNone(select([capture('GET','/',a,'body',vary='x')],'GET','/',b,0))
    def test_missing_matches_missing(self): self.assertIsNotNone(select([capture('GET','/',{},'body',vary='x')],'GET','/',{},0))
    def test_nonvary_ignored(self): self.assertIsNotNone(select([entry()],'GET','/help',{'accept-language':'fr','x':'other'},11))
    def test_multifield(self):
        e=capture('GET','/',{'X':'1','Y':'2'},'b',vary=' y, X,x ')
        self.assertEqual(e['vary'],['x','y'])
        self.assertIsNone(select([e],'GET','/',{'x':'1','y':'3'},0))
        self.assertIsNotNone(select([e],'GET','/',{'x':'1','y':'2'},0))
    def test_empty_vary(self): self.assertIsNotNone(select([entry(vary='')],'GET','/help',{},11))
    def test_expiry_boundary(self): self.assertIsNone(select([entry()],'GET','/help',{'accept-language':'fr'},30))
    def test_before_expiry(self): self.assertIsNotNone(select([entry()],'GET','/help',{'accept-language':'fr'},29.999))
    def test_future_not_fresh(self): self.assertIsNone(select([entry()],'GET','/help',{'accept-language':'fr'},9))
    def test_zero_age(self): self.assertIsNone(select([entry(max_age=0)],'GET','/help',{'accept-language':'fr'},10))
    def test_url_exact(self): self.assertIsNone(select([entry()],'GET','/help?x=1',{'accept-language':'fr'},11))
    def test_method_exact(self):
        for m in ['POST','HEAD','get']: self.assertIsNone(select([entry()],m,'/help',{},11))
    def test_latest_time_not_index(self):
        a,b=entry(stored_at=12),entry(stored_at=10)
        a['body']='new';b['body']='old'
        self.assertEqual(select([a,b],'GET','/help',{'accept-language':'fr'},13)['body'],'new')
    def test_last_index_tie(self):
        a,b=entry(),entry();b['body']='last'
        self.assertEqual(select([a,b],'GET','/help',{'accept-language':'fr'},13)['body'],'last')
    def test_stale_latest_does_not_mask_fresh(self):
        a,b=entry(),entry(stored_at=12,max_age=1)
        b['body']='stale'
        self.assertEqual(select([a,b],'GET','/help',{'accept-language':'fr'},15)['body'],'Bonjour')
    def test_copy(self):
        h={'X':'old'};e=capture('GET','/',h,'body',vary='x');h['X']='new'
        self.assertEqual(e['request_headers']['x'],'old')
        inputs=[e];before=copy.deepcopy(inputs);result=select(inputs,'GET','/',{'x':'old'},0)
        result['request_headers']['x']='bad';result['vary'].append('z')
        self.assertEqual(inputs,before)
    def test_capture_excluded(self):
        for kwargs in [{'vary':'*'},{'vary':'X, *'},{'cache_control':'NO-STORE'},{'cache_control':'public, no-store'}]:
            self.assertIsNone(capture('GET','/',{},'b',**kwargs))
        self.assertIsNone(capture('POST','/',{},'b'))
    def test_empty_cache(self): self.assertIsNone(select([],'GET','/',{},0))

class Invalid(unittest.TestCase):
    def test_bad_headers(self):
        for h in [None,[],{'x':1},{'x':'a\nb'},{'x':'a\rb'},{'x y':'a'},{'x':'a','X':'a'},{1:'a'}]:
            with self.subTest(h=h),self.assertRaises(ValueError): capture('GET','/',h,'b')
    def test_bad_vary(self):
        for v in [None,1,[], ' ', 'x,',',x','x,,y','x y','x:y','x\ny']:
            with self.subTest(v=v),self.assertRaises(ValueError): capture('GET','/',{},'b',vary=v)
    def test_bad_control(self):
        for c in ['max-age=60','private','public,',None,1,' ','no-cache']:
            with self.subTest(c=c),self.assertRaises(ValueError): capture('GET','/',{},'b',cache_control=c)
    def test_bad_times(self):
        for n in [True,-1,float('nan'),float('inf'),'1',None,10**1000]:
            for key in ['stored_at','max_age']:
                with self.subTest(n=n,key=key),self.assertRaises(ValueError): entry(**{key:n})
            with self.assertRaises(ValueError): select([],'GET','/',{},n)
    def test_overflow_expiry(self):
        with self.assertRaises(ValueError): entry(stored_at=1e308,max_age=1e308)
    def test_bad_request(self):
        for m,u in [('', '/'),('GET X','/'),(None,'/'),('GET',''),('GET',None),('GET','/\nx')]:
            with self.subTest(m=m,u=u),self.assertRaises(ValueError): select([],m,u,{},0)
    def test_bad_body(self):
        with self.assertRaises(ValueError): capture('GET','/',{},[]) 
    def test_all_records_validated(self):
        for bad in [None,{},dict(entry(),extra=1),dict(entry(),vary=['X']),dict(entry(),vary=['x','x']),dict(entry(),vary=['*']),dict(entry(),request_headers={'X':'x'}),dict(entry(),method='POST')]:
            with self.subTest(bad=bad),self.assertRaises(ValueError): select([entry(),bad],'GET','/help',{'accept-language':'fr'},11)
    def test_invalid_container(self):
        for es in [None,(),{}]:
            with self.assertRaises(ValueError): select(es,'GET','/',{},0)

class Exhaustive(unittest.TestCase):
    def test_small_variant_matrix(self):
        # Independent presence-and-value oracle over all subsets of two Vary names.
        values=[None,'','en','fr'];checks=0
        for va,vb in itertools.product(values,repeat=2):
            stored={k:v for k,v in zip(['x','y'],[va,vb]) if v is not None}
            for names in [[],['x'],['y'],['x','y']]:
                e=capture('GET','/',stored,'body',vary=','.join(names),stored_at=2,max_age=3)
                for ia,ib in itertools.product(values,repeat=2):
                    incoming={k:v for k,v in zip(['x','y'],[ia,ib]) if v is not None}
                    for now in [1,2,4.99,5,6]:
                        expected=2<=now<5 and all((k in stored,k and stored.get(k))==(k in incoming,k and incoming.get(k)) for k in names)
                        actual=select([e],'GET','/',incoming,now)
                        self.assertEqual(actual is not None,expected,(stored,names,incoming,now));checks+=1
        self.assertEqual(checks,5120)

if __name__=='__main__': unittest.main()
